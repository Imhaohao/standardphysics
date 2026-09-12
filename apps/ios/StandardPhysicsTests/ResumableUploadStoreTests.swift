import XCTest
@testable import StandardPhysics

final class ResumableUploadStoreTests: XCTestCase {
    private let apiBaseURL = URL(string: "https://standard.physics")!

    func testCompletedArtifactsSurviveAStoreRestart() throws {
        let directory = try makeDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let scanID = UUID()

        var store = ResumableUploadStore(captureDirectory: directory)
        try store.begin(scanID: scanID, apiBaseURL: apiBaseURL)
        try store.recordUploaded(artifactID: "room-json")

        let restored = ResumableUploadStore(captureDirectory: directory)
        XCTAssertEqual(restored.scanID, scanID)
        XCTAssertEqual(restored.completedArtifactIDs, ["room-json"])
        XCTAssertFalse(restored.needsUpload(artifactID: "room-json"))
        XCTAssertTrue(restored.needsUpload(artifactID: "walkthrough"))
    }

    func testLegacyUUIDStateDecodesWithoutDiscardingReceipts() throws {
        let directory = try makeDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let scanID = UUID()
        let legacyState = """
        {"scanID":"\(scanID.uuidString)","completedArtifactIDs":["room-json"],"isFinalized":true,"lastServerState":"checking"}
        """
        try Data(legacyState.utf8).write(to: directory.appendingPathComponent("upload-state.json"))

        let restored = ResumableUploadStore(captureDirectory: directory)
        XCTAssertEqual(restored.scanID, scanID)
        XCTAssertEqual(restored.completedArtifactIDs, ["room-json"])
        XCTAssertTrue(restored.isFinalized)
        XCTAssertEqual(restored.lastServerState, .checking)
    }

    func testLegacyReceiptBindsOnFirstUseAndRejectsLaterEndpointChanges() throws {
        let directory = try makeDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let scanID = UUID()
        let legacyState = """
        {"scanID":"\(scanID.uuidString)","completedArtifactIDs":["room-json"]}
        """
        try Data(legacyState.utf8).write(to: directory.appendingPathComponent("upload-state.json"))
        var store = ResumableUploadStore(captureDirectory: directory)

        try store.bindOrValidate(apiBaseURL: apiBaseURL)
        XCTAssertEqual(store.apiBaseURL, apiBaseURL)
        XCTAssertThrowsError(
            try store.bindOrValidate(apiBaseURL: URL(string: "https://other.standard.physics")!)
        ) { error in
            XCTAssertEqual(error as? UploadStoreError, .apiBaseURLMismatch)
        }
        XCTAssertEqual(ResumableUploadStore(captureDirectory: directory).apiBaseURL, apiBaseURL)
    }

    func testTerminalFailedReplacementPreservesOldRemoteAndResetsReceipts() throws {
        let directory = try makeDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let oldScanID = UUID()
        let newScanID = UUID()
        var store = ResumableUploadStore(captureDirectory: directory)
        try store.begin(scanID: oldScanID, apiBaseURL: apiBaseURL)
        try store.recordUploaded(artifactID: "room-json")
        try store.recordFinalized()
        try store.record(state: .failed)

        try store.replaceRemoteScan(with: newScanID, apiBaseURL: apiBaseURL)

        let restored = ResumableUploadStore(captureDirectory: directory)
        XCTAssertEqual(restored.scanID, newScanID)
        XCTAssertEqual(restored.previousScanIDs, [oldScanID])
        XCTAssertTrue(restored.completedArtifactIDs.isEmpty)
        XCTAssertFalse(restored.isFinalized)
        XCTAssertNil(restored.lastServerState)
    }

    func testPersistenceFailureDoesNotCommitMemory() throws {
        let fileURL = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try Data().write(to: fileURL)
        defer { try? FileManager.default.removeItem(at: fileURL) }
        let scanID = UUID()
        var store = ResumableUploadStore(captureDirectory: fileURL)

        XCTAssertThrowsError(try store.begin(scanID: scanID, apiBaseURL: apiBaseURL))
        XCTAssertNil(store.scanID)
        XCTAssertTrue(store.completedArtifactIDs.isEmpty)
        XCTAssertFalse(store.isFinalized)
    }

    func testLatestServerStateSurvivesAStoreRestart() throws {
        let directory = try makeDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        var store = ResumableUploadStore(captureDirectory: directory)
        XCTAssertEqual(store.historyText, "Saved on this phone")
        try store.begin(scanID: UUID(), apiBaseURL: apiBaseURL)
        try store.recordFinalized()
        try store.record(state: .checking)

        let restored = ResumableUploadStore(captureDirectory: directory)
        XCTAssertEqual(restored.historyText, "Checking")
        XCTAssertTrue(restored.shouldPollServer)
        var completed = restored
        try completed.record(state: .ready)
        XCTAssertFalse(completed.shouldPollServer)
    }

    private func makeDirectory() throws -> URL {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory
    }
}
