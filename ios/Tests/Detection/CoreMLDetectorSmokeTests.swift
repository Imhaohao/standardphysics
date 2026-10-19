import CoreGraphics
import CoreVideo
import ImageIO
import XCTest
@testable import StandardPhysics

/// Runs the bundled model on a real photo. Point `SP_DETECTOR_SMOKE_IMAGE` at COCO val2017
/// image 000000000139 (a living room with chairs, a person and a television); pass it to
/// xcodebuild as `TEST_RUNNER_SP_DETECTOR_SMOKE_IMAGE`.
final class CoreMLDetectorSmokeTests: XCTestCase {
    private static let imagePathKey = "SP_DETECTOR_SMOKE_IMAGE"
    private static let warmUpRuns = 2
    private static let timedRuns = 10

    private func smokeImage() throws -> CVPixelBufferWrapper {
        guard let path = ProcessInfo.processInfo.environment[Self.imagePathKey] else {
            throw XCTSkip("Set \(Self.imagePathKey) to a COCO photo to run the detector smoke test")
        }
        let source = try XCTUnwrap(CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil))
        let image = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
        return CVPixelBufferWrapper(buffer: try Self.bgraBuffer(drawing: image))
    }

    private func loadedDetector() async throws -> CoreMLDetector {
        let detector = CoreMLDetector(bundle: .main)
        guard await detector.isModelAvailable else {
            throw XCTSkip("No ObjectDetector model bundled; run ios/scripts/export-detector.sh")
        }
        return detector
    }

    func testFindsChairsAndATelevisionInALivingRoom() async throws {
        let frame = try smokeImage()
        let detections = try await loadedDetector().detect(pixelBuffer: frame)
        let categories = Set(detections.map(\.category))
        XCTAssertTrue(categories.contains("chair"), "found \(categories)")
        XCTAssertTrue(categories.contains("television"), "found \(categories)")
        let television = try XCTUnwrap(detections.first { $0.category == "television" })
        XCTAssertLessThan(television.boundingBox.midX, 0.3, "the large television sits on the left of the photo")
    }

    func testReportsLatencyOnThisDevice() async throws {
        let frame = try smokeImage()
        let detector = try await loadedDetector()
        for _ in 0..<Self.warmUpRuns {
            _ = try await detector.detect(pixelBuffer: frame)
        }
        let clock = ContinuousClock()
        var milliseconds: [Double] = []
        for _ in 0..<Self.timedRuns {
            let elapsed = try await clock.measure { _ = try await detector.detect(pixelBuffer: frame) }
            milliseconds.append(Double(elapsed.components.seconds) * 1000 + Double(elapsed.components.attoseconds) / 1e15)
        }
        let sorted = milliseconds.sorted()
        print("Detector latency ms: median \(sorted[sorted.count / 2]), min \(sorted[0]), max \(sorted[sorted.count - 1])")
    }

    private static func bgraBuffer(drawing image: CGImage) throws -> CVPixelBuffer {
        var buffer: CVPixelBuffer?
        let status = CVPixelBufferCreate(kCFAllocatorDefault, image.width, image.height, kCVPixelFormatType_32BGRA, nil, &buffer)
        XCTAssertEqual(status, kCVReturnSuccess)
        let pixelBuffer = try XCTUnwrap(buffer)
        CVPixelBufferLockBaseAddress(pixelBuffer, [])
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, []) }
        let context = try XCTUnwrap(CGContext(
            data: CVPixelBufferGetBaseAddress(pixelBuffer),
            width: image.width,
            height: image.height,
            bitsPerComponent: 8,
            bytesPerRow: CVPixelBufferGetBytesPerRow(pixelBuffer),
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue
        ))
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        return pixelBuffer
    }
}
