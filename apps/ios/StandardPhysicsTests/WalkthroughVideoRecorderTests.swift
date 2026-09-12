import AVFoundation
import CoreVideo
import XCTest
@testable import StandardPhysics

final class WalkthroughVideoRecorderTests: XCTestCase {
    func testFinishesWithPlayableH264VideoAfterAppendingFrames() async throws {
        let directory = try makeTemporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let outputURL = directory.appendingPathComponent("walkthrough.mp4")
        let recorder = try WalkthroughVideoRecorder(outputURL: outputURL)
        let frame = try makePixelBuffer()

        XCTAssertTrue(recorder.append(pixelBuffer: frame, timestamp: 10))
        XCTAssertTrue(recorder.append(pixelBuffer: frame, timestamp: 10.1))

        let result = await finish(recorder)
        guard case .success(let videoURL?) = result else {
            return XCTFail("Expected a video URL, got \(result)")
        }

        let asset = AVAsset(url: videoURL)
        let isPlayable = try await asset.load(.isPlayable)
        let tracks = try await asset.loadTracks(withMediaType: .video)
        let duration = try await asset.load(.duration)
        XCTAssertTrue(isPlayable)
        XCTAssertFalse(tracks.isEmpty)
        XCTAssertGreaterThan(duration.seconds, 0)
    }

    func testFinishesSuccessfullyWithoutAFrame() async throws {
        let directory = try makeTemporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let outputURL = directory.appendingPathComponent("walkthrough.mp4")
        let recorder = try WalkthroughVideoRecorder(outputURL: outputURL)

        let result = await finish(recorder)
        guard case .success(nil) = result else {
            return XCTFail("Expected success(nil), got \(result)")
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: outputURL.path))
    }

    func testFinishIsIdempotentAndAppendAfterFinishIsRejected() async throws {
        let directory = try makeTemporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let recorder = try WalkthroughVideoRecorder(
            outputURL: directory.appendingPathComponent("walkthrough.mp4")
        )
        let frame = try makePixelBuffer()
        XCTAssertTrue(recorder.append(pixelBuffer: frame, timestamp: 0))

        let first = expectation(description: "first finish")
        let second = expectation(description: "second finish")
        let firstResult = ResultBox()
        let secondResult = ResultBox()
        recorder.finish {
            firstResult.value = $0
            first.fulfill()
        }
        recorder.finish {
            secondResult.value = $0
            second.fulfill()
        }
        XCTAssertFalse(recorder.append(pixelBuffer: frame, timestamp: 1))
        await fulfillment(of: [first, second], timeout: 10)

        guard case .success(let firstURL?) = firstResult.value,
              case .success(let secondURL?) = secondResult.value else {
            return XCTFail("Expected both finishes to succeed with a URL")
        }
        XCTAssertEqual(firstURL, secondURL)
    }

    func testCancelIsIdempotentAndFinishAfterCancelReturnsNoVideo() async throws {
        let directory = try makeTemporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let outputURL = directory.appendingPathComponent("walkthrough.mp4")
        let recorder = try WalkthroughVideoRecorder(outputURL: outputURL)
        let frame = try makePixelBuffer()
        XCTAssertTrue(recorder.append(pixelBuffer: frame, timestamp: 0))

        recorder.cancel()
        recorder.cancel()
        let result = await finish(recorder)
        guard case .success(nil) = result else {
            return XCTFail("Expected success(nil) after cancel, got \(result)")
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: outputURL.path))
    }

    private func finish(
        _ recorder: WalkthroughVideoRecorder,
        file: StaticString = #filePath,
        line: UInt = #line
    ) async -> Result<URL?, Error> {
        let expectation = expectation(description: "finish")
        let result = ResultBox()
        recorder.finish {
            result.value = $0
            expectation.fulfill()
        }
        await fulfillment(of: [expectation], timeout: 10)
        XCTAssertNotNil(result.value, file: file, line: line)
        return result.value!
    }

    private func makeTemporaryDirectory() throws -> URL {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true
        )
        return directory
    }

    private func makePixelBuffer() throws -> CVPixelBuffer {
        var pixelBuffer: CVPixelBuffer?
        let attributes: [CFString: Any] = [
            kCVPixelBufferIOSurfacePropertiesKey: [:],
            kCVPixelBufferMetalCompatibilityKey: true
        ]
        let status = CVPixelBufferCreate(
            nil,
            1_280,
            960,
            kCVPixelFormatType_32BGRA,
            attributes as CFDictionary,
            &pixelBuffer
        )
        guard status == kCVReturnSuccess, let pixelBuffer else {
            throw VideoRecorderError.pixelBufferAllocationFailed
        }
        CVPixelBufferLockBaseAddress(pixelBuffer, [])
        if let baseAddress = CVPixelBufferGetBaseAddress(pixelBuffer) {
            memset(baseAddress, 0x7f, CVPixelBufferGetDataSize(pixelBuffer))
        }
        CVPixelBufferUnlockBaseAddress(pixelBuffer, [])
        return pixelBuffer
    }
}

private final class ResultBox: @unchecked Sendable {
    var value: Result<URL?, Error>?
}
