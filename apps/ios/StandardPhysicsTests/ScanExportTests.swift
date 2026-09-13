import RoomPlan
import XCTest
@testable import StandardPhysics

final class ScanExportTests: XCTestCase {
    func testRealRoomExportsAndCanBeRecoveredWithoutVideo() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let source = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "apple_bedroom3.room", withExtension: "json"))
        let room = try JSONDecoder().decode(CapturedRoom.self, from: Data(contentsOf: source))
        try JSONEncoder().encode(room).write(to: directory.appendingPathComponent("room.recovery.json"))
        let recovered = try CaptureRecovery.recover(from: directory)
        XCTAssertTrue(FileManager.default.fileExists(atPath: recovered.roomURL.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appendingPathComponent("capture.json").path))
        XCTAssertFalse(recovered.artifacts.contains { $0.kind == .walkthroughMP4 })
        XCTAssertNotNil(recovered.captureNotice)
        let coverageURL = try XCTUnwrap(recovered.artifacts.first { $0.kind == .coverage }?.fileURL)
        let coverage = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: coverageURL)) as? [String: Any])
        let expectedIdentifiers = Set(RoomCoverage.snapshots(from: room).map(\.id))
        XCTAssertEqual(Set(coverage.keys), Set(expectedIdentifiers.map(\.uuidString)))
        let metadataURL = try XCTUnwrap(recovered.artifacts.first { $0.kind == .roomMetadata }?.fileURL)
        let metadata = try PropertyListSerialization.propertyList(from: Data(contentsOf: metadataURL), format: nil)
        let nodeMap = try XCTUnwrap(metadata as? [String: String])
        let mappedIdentifiers = try Set(nodeMap.values.map { try XCTUnwrap(UUID(uuidString: $0)) })
        XCTAssertEqual(mappedIdentifiers, expectedIdentifiers)
        XCTAssertEqual(nodeMap.count, expectedIdentifiers.count)
        let saved = try JSONDecoder().decode(CapturedScan.self,
            from: Data(contentsOf: directory.appendingPathComponent("capture.json")))
        XCTAssertEqual(saved.id, UUID(uuidString: directory.lastPathComponent))
        let secondRecovery = try CaptureRecovery.recover(from: directory)
        XCTAssertEqual(secondRecovery.id, saved.id)
        XCTAssertEqual(saved.artifacts.count, 5)

        let notice = "Your room is saved. Record another pass to add the missing images."
        let recording = RecordingResult(videoURL: nil, frameURLs: [],
            posesURL: directory.appendingPathComponent("poses.json"), duration: 0, captureNotice: notice)
        let warnedScan = try ScanExporter.export(room: room, recording: recording,
            coverage: CoverageSnapshot(), directory: directory)
        XCTAssertEqual(try warnedScan.renamed("Recovered room").captureNotice, notice)
    }
}
