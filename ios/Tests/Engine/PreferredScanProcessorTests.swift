import XCTest
@testable import StandardPhysics

@MainActor
final class PreferredScanProcessorTests: XCTestCase {
    private final class RecordingProcessor: ScanProcessing {
        let error: Error?
        private(set) var calls = 0

        init(error: Error? = nil) {
            self.error = error
        }

        func process(_ manifest: ScanManifest, onUpdate: @escaping (ProcessingUpdate) -> Void) async throws -> ScanReport {
            calls += 1
            if let error { throw error }
            return SampleData.report(for: manifest)
        }
    }

    private struct ServerDown: Error {}

    private let manifest = SampleData.unfinishedManifest()

    func testSignedOutOwnersAreCheckedOnTheirPhone() async throws {
        let remote = RecordingProcessor()
        let local = RecordingProcessor()
        let processor = PreferredScanProcessor(remote: remote, local: local, isSignedIn: { false })
        _ = try await processor.process(manifest) { _ in }
        XCTAssertEqual(remote.calls, 0)
        XCTAssertEqual(local.calls, 1)
    }

    func testSignedInOwnersGetTheServerAssessment() async throws {
        let remote = RecordingProcessor()
        let local = RecordingProcessor()
        let processor = PreferredScanProcessor(remote: remote, local: local, isSignedIn: { true })
        _ = try await processor.process(manifest) { _ in }
        XCTAssertEqual(remote.calls, 1)
        XCTAssertEqual(local.calls, 0)
    }

    func testAServerFailureFallsBackToThePhone() async throws {
        let remote = RecordingProcessor(error: ServerDown())
        let local = RecordingProcessor()
        let processor = PreferredScanProcessor(remote: remote, local: local, isSignedIn: { true })
        _ = try await processor.process(manifest) { _ in }
        XCTAssertEqual(local.calls, 1)
    }

    func testCancellationIsNotRetriedLocally() async {
        let remote = RecordingProcessor(error: CancellationError())
        let local = RecordingProcessor()
        let processor = PreferredScanProcessor(remote: remote, local: local, isSignedIn: { true })
        do {
            _ = try await processor.process(manifest) { _ in }
            XCTFail("expected cancellation")
        } catch {
            XCTAssertTrue(error is CancellationError)
        }
        XCTAssertEqual(local.calls, 0)
    }
}
