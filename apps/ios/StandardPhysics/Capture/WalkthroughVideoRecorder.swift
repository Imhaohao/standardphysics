import AVFoundation
import CoreImage

/// Encodes the camera walkthrough without retaining an unbounded number of
/// camera buffers while AVAssetWriter applies backpressure.
final class WalkthroughVideoRecorder: @unchecked Sendable {
    private static let maxPendingAppends = 3

    private let writer: AVAssetWriter
    private let input: AVAssetWriterInput
    private let adaptor: AVAssetWriterInputPixelBufferAdaptor
    private let queue = DispatchQueue(label: "com.standardphysics.walkthrough", qos: .userInitiated)
    private let stateLock = NSLock()
    private let context = CIContext(options: [.cacheIntermediates: false])
    private let outputURL: URL

    // These properties are accessed only on queue, except for the small
    // admission/lifecycle counters protected by stateLock.
    private var firstTimestamp: TimeInterval?
    private var appendedFrameCount = 0
    private var recordedError: Error?
    private var pendingAppends = 0
    private var finishStarted = false
    private var cancelRequested = false
    private var terminalResult: Result<URL?, Error>?
    private var finishCompletions: [(@Sendable (Result<URL?, Error>) -> Void)] = []

    init(outputURL: URL) throws {
        self.outputURL = outputURL
        try? FileManager.default.removeItem(at: outputURL)
        writer = try AVAssetWriter(outputURL: outputURL, fileType: .mp4)
        input = AVAssetWriterInput(
            mediaType: .video,
            outputSettings: [
                AVVideoCodecKey: AVVideoCodecType.h264,
                AVVideoWidthKey: 1_280,
                AVVideoHeightKey: 960,
                AVVideoCompressionPropertiesKey: [
                    AVVideoAverageBitRateKey: 4_000_000,
                    AVVideoExpectedSourceFrameRateKey: 15,
                    AVVideoMaxKeyFrameIntervalKey: 30
                ]
            ]
        )
        input.expectsMediaDataInRealTime = true
        adaptor = AVAssetWriterInputPixelBufferAdaptor(
            assetWriterInput: input,
            sourcePixelBufferAttributes: [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
                kCVPixelBufferWidthKey as String: 1_280,
                kCVPixelBufferHeightKey as String: 960,
                kCVPixelBufferIOSurfacePropertiesKey as String: [:]
            ]
        )
        guard writer.canAdd(input) else { throw VideoRecorderError.cannotAddInput }
        writer.add(input)
    }

    /// Returns whether the frame was admitted to the bounded encoding queue.
    /// An admitted frame can still fail during encoding; that failure is
    /// reported by finish.
    @discardableResult
    func append(pixelBuffer: CVPixelBuffer, timestamp: TimeInterval) -> Bool {
        let transferableBuffer = SendablePixelBuffer(pixelBuffer)
        stateLock.lock()
        guard !finishStarted,
              !cancelRequested,
              pendingAppends < Self.maxPendingAppends else {
            stateLock.unlock()
            return false
        }
        pendingAppends += 1
        queue.async { [self] in
            defer { releasePendingAppend() }
            process(transferableBuffer.value, timestamp: timestamp)
        }
        // Keep this unlock after queue submission. finish/cancel use the same
        // lock, so their terminal block cannot overtake an admitted append.
        stateLock.unlock()
        return true
    }

    /// Finishes the writer. A recording with no successfully appended frames
    /// is a valid result and returns success(nil).
    func finish(completion: @escaping @Sendable (Result<URL?, Error>) -> Void) {
        stateLock.lock()
        if let terminalResult {
            stateLock.unlock()
            deliver(completion, result: terminalResult)
            return
        }
        finishCompletions.append(completion)
        guard !finishStarted else {
            stateLock.unlock()
            return
        }
        finishStarted = true
        stateLock.unlock()

        // This block runs after all appends admitted before finish, because
        // both operations use the same serial queue.
        queue.async { [self] in finalize()
        }
    }

    /// Cancels pending work and discards the output. It is safe to call more
    /// than once, including concurrently with finish.
    func cancel() {
        stateLock.lock()
        guard terminalResult == nil, !finishStarted else {
            stateLock.unlock()
            return
        }
        finishStarted = true
        cancelRequested = true
        stateLock.unlock()

        queue.async { [self] in
            if writer.status == .writing {
                writer.cancelWriting()
            }
            try? FileManager.default.removeItem(at: outputURL)
            complete(.success(nil))
        }
    }

    private func process(_ source: CVPixelBuffer, timestamp: TimeInterval) {
        guard timestamp.isFinite else {
            record(VideoRecorderError.invalidTimestamp)
            return
        }

        // Starting before checking readiness is intentional. Checking
        // isReadyForMoreMediaData while the writer is still .unknown causes
        // the first frame to be dropped forever on device.
        if writer.status == .unknown {
            guard writer.startWriting() else {
                record(writer.error ?? VideoRecorderError.writerStartFailed)
                return
            }
            firstTimestamp = timestamp
            writer.startSession(atSourceTime: .zero)
        }

        guard writer.status == .writing,
              input.isReadyForMoreMediaData else {
            return
        }
        guard let firstTimestamp else {
            record(VideoRecorderError.writerStartFailed)
            return
        }
        guard let pool = adaptor.pixelBufferPool else {
            record(VideoRecorderError.pixelBufferPoolUnavailable)
            return
        }

        var outputBuffer: CVPixelBuffer?
        guard CVPixelBufferPoolCreatePixelBuffer(nil, pool, &outputBuffer) == kCVReturnSuccess,
              let outputBuffer else {
            record(VideoRecorderError.pixelBufferAllocationFailed)
            return
        }
        render(source, into: outputBuffer)

        let presentationTime = CMTime(
            seconds: max(0, timestamp - firstTimestamp),
            preferredTimescale: 600
        )
        guard adaptor.append(outputBuffer, withPresentationTime: presentationTime) else {
            record(writer.error ?? VideoRecorderError.appendFailed)
            return
        }
        appendedFrameCount += 1
    }

    private func finalize() {
        guard !cancelRequested else {
            if writer.status == .writing {
                writer.cancelWriting()
            }
            try? FileManager.default.removeItem(at: outputURL)
            complete(.success(nil))
            return
        }

        // No successful append means there is no video artifact. If a writer
        // was started for a frame that arrived while the input was busy, stop
        // it without manufacturing an empty MP4.
        guard appendedFrameCount > 0 else {
            if writer.status == .writing {
                writer.cancelWriting()
            }
            try? FileManager.default.removeItem(at: outputURL)
            complete(recordedError.map(Result.failure) ?? .success(nil))
            return
        }

        input.markAsFinished()
        let encodingError = recordedError
        writer.finishWriting { [self] in
            let result: Result<URL?, Error>
            if let encodingError {
                result = .failure(encodingError)
            } else if let writerError = writer.error {
                result = .failure(writerError)
            } else if writer.status == .completed,
                      FileManager.default.fileExists(atPath: outputURL.path) {
                result = .success(outputURL)
            } else {
                result = .failure(VideoRecorderError.writerFinishFailed)
            }
            complete(result)
        }
    }

    private func releasePendingAppend() {
        stateLock.lock()
        pendingAppends -= 1
        stateLock.unlock()
    }

    private func record(_ error: Error) {
        recordedError = recordedError ?? error
    }

    private func complete(_ result: Result<URL?, Error>) {
        stateLock.lock()
        guard terminalResult == nil else {
            stateLock.unlock()
            return
        }
        terminalResult = result
        let completions = finishCompletions
        finishCompletions.removeAll()
        stateLock.unlock()

        for completion in completions {
            deliver(completion, result: result)
        }
    }

    private func deliver(
        _ completion: @escaping @Sendable (Result<URL?, Error>) -> Void,
        result: Result<URL?, Error>
    ) {
        DispatchQueue.main.async {
            completion(result)
        }
    }

    private func render(_ source: CVPixelBuffer, into destination: CVPixelBuffer) {
        let image = CIImage(cvPixelBuffer: source)
        let target = CGRect(x: 0, y: 0, width: 1_280, height: 960)
        let scale = max(target.width / image.extent.width, target.height / image.extent.height)
        let scaled = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        let offset = CGAffineTransform(
            translationX: (target.width - scaled.extent.width) / 2,
            y: (target.height - scaled.extent.height) / 2
        )
        context.render(
            scaled.transformed(by: offset),
            to: destination,
            bounds: target,
            colorSpace: CGColorSpaceCreateDeviceRGB()
        )
    }
}

struct SendablePixelBuffer: @unchecked Sendable {
    let value: CVPixelBuffer

    init(_ value: CVPixelBuffer) {
        self.value = value
    }
}

enum VideoRecorderError: Error {
    case cannotAddInput
    case writerStartFailed
    case writerFinishFailed
    case appendFailed
    case pixelBufferPoolUnavailable
    case pixelBufferAllocationFailed
    case invalidTimestamp
}
