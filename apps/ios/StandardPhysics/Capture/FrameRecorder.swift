import ARKit
import AVFoundation
import CoreImage
import UIKit

struct PoseRecord: Codable, Sendable {
    let image: String
    let timestamp: TimeInterval
    let transform: [Float]
    let intrinsics: [Float]
    let orientation: String
}

struct RecordingResult: Sendable {
    let videoURL: URL?
    let frameURLs: [URL]
    let posesURL: URL
    let duration: TimeInterval
}

@MainActor
final class FrameRecorder: NSObject {
    private let session: ARSession
    private let directory: URL
    private let framesDirectory: URL
    private let videoRecorder: WalkthroughVideoRecorder
    private let imageContext = CIContext(options: [.cacheIntermediates: false])
    private let imageQueue = DispatchQueue(label: "com.standardphysics.keyframes", qos: .utility)
    private let recordingFailures = RecordingFailureState()
    private var displayLink: CADisplayLink?
    private var poseRecords: [PoseRecord] = []
    private var frameURLs: [URL] = []
    private var startUptime: TimeInterval?
    private var startTimestamp: TimeInterval?
    private var lastVideoTimestamp: TimeInterval = -.infinity
    private var lastKeyframeTimestamp: TimeInterval = -.infinity
    private var hasReachedTimeLimit = false

    var onTimeLimit: (() -> Void)?

    init(session: ARSession, directory: URL) throws {
        self.session = session
        self.directory = directory
        framesDirectory = directory.appendingPathComponent("frames", isDirectory: true)
        try FileManager.default.createDirectory(at: framesDirectory, withIntermediateDirectories: true)
        videoRecorder = try WalkthroughVideoRecorder(
            outputURL: directory.appendingPathComponent("walkthrough.mp4")
        )
    }

    func start() {
        guard displayLink == nil else { return }
        startUptime = ProcessInfo.processInfo.systemUptime
        let link = CADisplayLink(target: self, selector: #selector(sampleFrame))
        link.add(to: .main, forMode: .common)
        displayLink = link
    }

    func stop(completion: @escaping @MainActor (Result<RecordingResult, Error>) -> Void) {
        displayLink?.invalidate()
        displayLink = nil
        let duration = max(0, (session.currentFrame?.timestamp ?? startTimestamp ?? 0) - (startTimestamp ?? 0))

        let completionGroup = DispatchGroup()
        let stopResults = RecordingStopResults()
        let poses = poseRecords
        let completedFrameURLs = frameURLs
        let outputDirectory = directory
        let failures = recordingFailures
        completionGroup.enter()
        videoRecorder.finish { result in
            stopResults.setVideoResult(result.map(Optional.some))
            completionGroup.leave()
        }

        completionGroup.enter()
        imageQueue.async {
            do {
                if let error = failures.first { throw error }
                let posesURL = outputDirectory.appendingPathComponent("poses.json")
                let data = try JSONEncoder.standardPhysics.encode(poses)
                try data.write(to: posesURL, options: .atomic)
            } catch {
                stopResults.setRecordingError(error)
            }
            completionGroup.leave()
        }

        completionGroup.notify(queue: .main) {
            let result = stopResults.makeResult(
                frameURLs: completedFrameURLs,
                directory: outputDirectory,
                duration: duration
            )
            MainActor.assumeIsolated {
                completion(result)
            }
        }
    }

    @objc private func sampleFrame() {
        guard let startUptime else { return }
        guard ProcessInfo.processInfo.systemUptime - startUptime < 240 else {
            guard !hasReachedTimeLimit else { return }
            hasReachedTimeLimit = true
            onTimeLimit?()
            return
        }
        guard let frame = session.currentFrame, frame.camera.trackingState.isUsable else { return }
        let startedAt = startTimestamp ?? frame.timestamp
        startTimestamp = startedAt

        let targetRate = ProcessInfo.processInfo.thermalState.rawValue >= ProcessInfo.ThermalState.serious.rawValue
            ? 10.0
            : 15.0
        if frame.timestamp - lastVideoTimestamp >= 1.0 / targetRate {
            lastVideoTimestamp = frame.timestamp
            videoRecorder.append(pixelBuffer: frame.capturedImage, timestamp: frame.timestamp)
        }
        if frame.timestamp - lastKeyframeTimestamp >= 0.5 {
            lastKeyframeTimestamp = frame.timestamp
            saveKeyframe(frame)
        }
    }

    private func saveKeyframe(_ frame: ARFrame) {
        let sequence = poseRecords.count
        let filename = String(format: "frame_%04d.jpg", sequence)
        let fileURL = framesDirectory.appendingPathComponent(filename)
        poseRecords.append(PoseRecord(
            image: "frames/\(filename)",
            timestamp: frame.timestamp,
            transform: frame.camera.transform.flattened,
            intrinsics: frame.camera.intrinsics.flattened,
            orientation: UIApplication.shared.interfaceOrientation.name
        ))
        frameURLs.append(fileURL)

        let pixelBuffer = SendablePixelBuffer(frame.capturedImage)
        imageQueue.async { [imageContext, recordingFailures] in
            let image = CIImage(cvPixelBuffer: pixelBuffer.value)
            guard let cgImage = imageContext.createCGImage(image, from: image.extent),
                  let data = UIImage(cgImage: cgImage).jpegData(compressionQuality: 0.9) else {
                recordingFailures.record(FrameRecorderError.jpegEncodingFailed)
                return
            }
            do {
                try data.write(to: fileURL, options: .atomic)
            } catch {
                recordingFailures.record(error)
            }
        }
    }
}

private final class RecordingFailureState: @unchecked Sendable {
    private let lock = NSLock()
    private var errors: [Error] = []

    var first: Error? {
        lock.withLock { errors.first }
    }

    func record(_ error: Error) {
        lock.withLock { errors.append(error) }
    }
}

private final class RecordingStopResults: @unchecked Sendable {
    private let lock = NSLock()
    private var videoResult: Result<URL?, Error> = .success(nil)
    private var recordingError: Error?

    func setVideoResult(_ result: Result<URL?, Error>) {
        lock.withLock { videoResult = result }
    }

    func setRecordingError(_ error: Error) {
        lock.withLock { recordingError = error }
    }

    func makeResult(
        frameURLs: [URL],
        directory: URL,
        duration: TimeInterval
    ) -> Result<RecordingResult, Error> {
        lock.withLock {
            if let recordingError { return .failure(recordingError) }
            return videoResult.map { videoURL in
                RecordingResult(
                    videoURL: videoURL,
                    frameURLs: frameURLs.sorted { $0.lastPathComponent < $1.lastPathComponent },
                    posesURL: directory.appendingPathComponent("poses.json"),
                    duration: duration
                )
            }
        }
    }
}

private enum FrameRecorderError: Error {
    case jpegEncodingFailed
}

private extension ARCamera.TrackingState {
    var isUsable: Bool {
        if case .normal = self { return true }
        return false
    }
}

private extension UIApplication {
    var interfaceOrientation: UIInterfaceOrientation {
        connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first(where: { $0.activationState == .foregroundActive })?
            .interfaceOrientation ?? .portrait
    }
}

private extension UIInterfaceOrientation {
    var name: String {
        switch self {
        case .portrait: "portrait"
        case .portraitUpsideDown: "portrait_upside_down"
        case .landscapeLeft: "landscape_left"
        case .landscapeRight: "landscape_right"
        default: "unknown"
        }
    }
}

extension simd_float4x4 {
    var flattened: [Float] {
        [columns.0, columns.1, columns.2, columns.3].flatMap { [$0.x, $0.y, $0.z, $0.w] }
    }
}

extension simd_float3x3 {
    var flattened: [Float] {
        [columns.0, columns.1, columns.2].flatMap { [$0.x, $0.y, $0.z] }
    }
}

extension JSONEncoder {
    static var standardPhysics: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return encoder
    }
}
