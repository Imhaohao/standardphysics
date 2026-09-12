import XCTest
@testable import StandardPhysics

final class ResumableUploadStoreTests: XCTestCase {
    func testCompletedArtifactsSurviveAStoreRestart() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        var store = ResumableUploadStore(captureDirectory: directory)
        try store.begin(scanID: "scan-123")
        try store.recordUploaded(artifactID: "room-json")

        let restored = ResumableUploadStore(captureDirectory: directory)
        XCTAssertEqual(restored.scanID, "scan-123")
        XCTAssertEqual(restored.completedArtifactIDs, ["room-json"])
        XCTAssertFalse(restored.needsUpload(artifactID: "room-json"))
        XCTAssertTrue(restored.needsUpload(artifactID: "walkthrough"))
    }

    func testLatestServerStateSurvivesAStoreRestart() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        var store = ResumableUploadStore(captureDirectory: directory)
        XCTAssertEqual(store.historyText, "Saved on this phone")
        try store.begin(scanID: "scan-123")
        try store.recordFinalized()
        try store.record(state: .checking)

        let restored = ResumableUploadStore(captureDirectory: directory)
        XCTAssertEqual(restored.historyText, "Checking")
        XCTAssertTrue(restored.shouldPollServer)
        var completed = restored
        try completed.record(state: .ready)
        XCTAssertFalse(completed.shouldPollServer)
    }
}
