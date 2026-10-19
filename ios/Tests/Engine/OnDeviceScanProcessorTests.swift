import XCTest
@testable import StandardPhysics

@MainActor
final class OnDeviceScanProcessorTests: XCTestCase {
    private var root: URL!

    override func setUp() async throws {
        root = FileManager.default.temporaryDirectory.appending(path: "processor-\(UUID().uuidString)")
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: root)
    }

    private func fixture(_ name: String) throws -> Data {
        let repoRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        return try Data(contentsOf: repoRoot.appending(path: "datasets/phone/\(name)/room.json"))
    }

    private func savedScan(rooms: [(String, String)]) async throws -> (FileScanJournal, ScanManifest) {
        let journal = FileScanJournal(root: root)
        var manifest = try await journal.create(name: "Corner Cafe")
        for (fixtureName, roomName) in rooms {
            manifest = try await journal.appendRoom(scanID: manifest.scanID, capturedRoomJSON: fixture(fixtureName), name: roomName)
        }
        return (journal, manifest)
    }

    func testTwoRealRoomsAreCheckedOnDeviceUnderTheTimeBudget() async throws {
        let (journal, manifest) = try await savedScan(rooms: [("test1", "Dining room"), ("ravida", "Back room")])
        let processor = OnDeviceScanProcessor(journal: journal)
        var stages: [ProcessingStage] = []

        let clock = ContinuousClock()
        var report: ScanReport?
        let elapsed = try await clock.measure {
            report = try await processor.process(manifest) { stages.append($0.stage) }
        }

        let checked = try XCTUnwrap(report)
        XCTAssertLessThan(elapsed, .seconds(5))
        XCTAssertFalse(checked.findings.isEmpty)
        XCTAssertEqual(checked.roomNames, ["Dining room", "Back room"])
        XCTAssertEqual(stages.last, .writing)
        XCTAssertEqual(Set(checked.findings.map(\.jurisdiction)), [.ada2010, .cbc11b])
    }

    func testEveryFindingHasANamedSubject() async throws {
        let (journal, manifest) = try await savedScan(rooms: [("test1", "Dining room")])
        let report = try await OnDeviceScanProcessor(journal: journal).process(manifest) { _ in }
        let unnamed = report.findings.filter { report.subjects[$0.subjectID] == nil }
        XCTAssertTrue(unnamed.isEmpty, "\(unnamed.prefix(3).map(\.subjectID))")
    }

    func testSavedDetectorObjectsAreCheckedAndNamed() async throws {
        let (journal, manifest) = try await savedScan(rooms: [("test1", "Dorm room")])
        let sink = DetectedObject(
            id: "detector-sink", category: "sink", label: "sink",
            center: ScenePoint(x: -5.0, y: 0.8, z: 0.2), size: ScenePoint(x: 0.6, y: 0.2, z: 0.5), confidence: 0.8, hits: 4
        )
        try await journal.saveDetectedObjects([sink], scanID: manifest.scanID, roomIndex: 0)

        let report = try await OnDeviceScanProcessor(journal: journal).process(manifest) { _ in }

        XCTAssertTrue(report.findings.contains { $0.subjectID == "detector-sink" })
        XCTAssertEqual(report.subjects["detector-sink"]?.label, "Sink")
        XCTAssertEqual(report.subjects["detector-sink"]?.roomName, "Dorm room")
    }

    func testAScanWithNoRoomsIsRefused() async throws {
        let (journal, manifest) = try await savedScan(rooms: [])
        do {
            _ = try await OnDeviceScanProcessor(journal: journal).process(manifest) { _ in }
            XCTFail("expected noRooms")
        } catch {
            XCTAssertEqual(error as? OnDeviceProcessingError, .noRooms)
        }
    }
}
