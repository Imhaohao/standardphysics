import AVFoundation
import CoreImage

final class WalkthroughVideoRecorder {
    private let writer: AVAssetWriter
    private let input: AVAssetWriterInput
    private let adaptor: AVAssetWriterInputPixelBufferAdaptor
    private let queue = DispatchQueue(label: "com.standardphysics.walkthrough", qos: .userInitiated)
    private let context = CIContext(options: [.cacheIntermediates: false])
    private let outputURL: URL
    private var firstTimestamp: TimeInterval?

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

    func append(pixelBuffer: CVPixelBuffer, timestamp: TimeInterval) {
        queue.async { [self] in
            guard input.isReadyForMoreMediaData else { return }
            if firstTimestamp == nil {
                firstTimestamp = timestamp
                guard writer.startWriting() else { return }
                writer.startSession(atSourceTime: .zero)
            }
            guard let firstTimestamp,
                  let pool = adaptor.pixelBufferPool else { return }

            var outputBuffer: CVPixelBuffer?
            guard CVPixelBufferPoolCreatePixelBuffer(nil, pool, &outputBuffer) == kCVReturnSuccess,
                  let outputBuffer else { return }
            render(pixelBuffer, into: outputBuffer)
            let presentationTime = CMTime(seconds: timestamp - firstTimestamp, preferredTimescale: 600)
            adaptor.append(outputBuffer, withPresentationTime: presentationTime)
        }
    }

    func finish(completion: @escaping (Result<URL, Error>) -> Void) {
        queue.async { [self] in
            guard firstTimestamp != nil else {
                DispatchQueue.main.async { completion(.failure(VideoRecorderError.noFrames)) }
                return
            }
            input.markAsFinished()
            writer.finishWriting {
                DispatchQueue.main.async {
                    if let error = self.writer.error {
                        completion(.failure(error))
                    } else {
                        completion(.success(self.outputURL))
                    }
                }
            }
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
        context.render(scaled.transformed(by: offset), to: destination, bounds: target, colorSpace: CGColorSpaceCreateDeviceRGB())
    }
}

enum VideoRecorderError: Error {
    case cannotAddInput
    case noFrames
}
