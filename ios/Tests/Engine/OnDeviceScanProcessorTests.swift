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
