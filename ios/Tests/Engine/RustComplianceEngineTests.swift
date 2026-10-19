import SPEngineKit
import XCTest
@testable import StandardPhysics

final class RustComplianceEngineTests: XCTestCase {
    private func fixtureRoom() throws -> Data {
        let repoRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        return try Data(contentsOf: repoRoot.appendingPathComponent("datasets/phone/test1/room.json"))
    }

    func testEngineFindingsCarryTitleSeverityAndRange() {
        let source = SpFinding(
            ruleId: "ADA-404", jurisdiction: "ADA2010", section: "404.2.3", title: "Door clear width", subjectId: "door",
            roomId: nil, status: .fail, measured: SpMeasured(text: "30 to 31 in", value: nil, lo: 30, hi: 31, unit: "in"),
            required: ">= 32 in", message: "Too narrow", evidence: "measured", severity: "violation", location: nil,
            counterpart: nil
        )
        let finding = Finding(source)
        XCTAssertEqual(finding.title, "Door clear width")
        XCTAssertEqual(finding.severity, .violation)
        XCTAssertEqual(finding.range, MeasuredRange(lo: 30, hi: 31, unit: "in"))
        XCTAssertNil(finding.counterpartRuleID, "the engine binding does not expose counterparts yet")
    }

    func testEngineJurisdictionsTheAppDoesNotKnowBecomeSystemChecks() {
        let source = SpFinding(
            ruleId: "x", jurisdiction: "SYSTEM", section: "", title: "", subjectId: "o", roomId: nil, status: .needsInfo,
            measured: nil, required: "", message: "m", evidence: "", severity: "info", location: nil,
            counterpart: "CBC-x"
        )
        let finding = Finding(source)
        XCTAssertEqual(finding.jurisdiction, .system)
        XCTAssertNil(finding.title)
        XCTAssertEqual(finding.severity, .info)
        XCTAssertEqual(finding.counterpartRuleID, "CBC-x")
    }

    func testRulepacksLoadFromTheAppBundle() throws {
        XCTAssertNoThrow(try RustComplianceEngine(bundle: .main))
    }

    func testRealRoomProducesFindingsForBothJurisdictions() async throws {
        let engine = try RustComplianceEngine(bundle: .main)
        let roomFindings = try await engine.evaluateRoom(capturedRoomJSON: fixtureRoom())
        XCTAssertFalse(roomFindings.isEmpty)

        let report = await engine.evaluateScan()
        let jurisdictions = Set(report.findings.map(\.jurisdiction))
        XCTAssertEqual(jurisdictions, [.ada2010, .cbc11b])
        XCTAssertFalse(report.reportJSON.isEmpty)
    }

    func testUnknownsAreNeverReportedAsPasses() async throws {
        let engine = try RustComplianceEngine(bundle: .main)
        _ = try await engine.evaluateRoom(capturedRoomJSON: fixtureRoom())
        let report = await engine.evaluateScan()
        let passesWithoutMeasurement = report.findings.filter { $0.status == .pass && $0.measured == nil }
        XCTAssertTrue(passesWithoutMeasurement.isEmpty, "\(passesWithoutMeasurement.prefix(3))")
    }

    func testFullRoomEvaluationIsFast() async throws {
        let engine = try RustComplianceEngine(bundle: .main)
        let room = try fixtureRoom()
        let clock = ContinuousClock()
        let elapsed = try await clock.measure {
            _ = try await engine.evaluateRoom(capturedRoomJSON: room)
            _ = await engine.evaluateScan()
        }
        XCTAssertLessThan(elapsed, .seconds(1))
    }

    private func detectedObjects() throws -> [DetectedObject] {
        let room = try XCTUnwrap(CapturedRoomGeometry(capturedRoomJSON: fixtureRoom()))
        let sinkCenter = SIMD3<Float>(-5.0, RepoFixtures.test1FloorLevel + 0.8, 0.2)
        let tracks = [
            RepoFixtures.track("refrigerator", at: RepoFixtures.test1Fridge),
            RepoFixtures.track("sink", at: sinkCenter, size: SIMD3(0.6, 0.2, 0.5)),
        ]
        var ids = ["detector-fridge", "detector-sink"].makeIterator()
        return DetectedObjects.finished(tracks: tracks, room: room) { ids.next() ?? "" }.objects
    }

    private struct SceneObject: Decodable {
        let id: String
        let category: String
        let source: String
        let center: ScenePoint
        let top_height: Double
    }

    private struct SceneRooms: Decodable {
        struct Room: Decodable { let objects: [SceneObject] }
        let rooms: [Room]
    }

    func testDetectorObjectsJoinTheRoomAtFloorHeightAndAreChecked() async throws {
        let engine = try RustComplianceEngine(bundle: .main)
        let roomFindings = try await engine.evaluateRoom(capturedRoomJSON: fixtureRoom(), detectedObjects: detectedObjects())

        let scene = try JSONDecoder().decode(SceneRooms.self, from: Data(await engine.sceneJSON().utf8))
        let objects = try XCTUnwrap(scene.rooms.first?.objects)
        XCTAssertEqual(objects.count, 18, "16 RoomPlan objects plus the fridge and the sink")
        let fridge = try XCTUnwrap(objects.first { $0.id == "detector-fridge" })
        XCTAssertEqual(fridge.category, "refrigerator")
        XCTAssertEqual(fridge.source, "detector")
        XCTAssertEqual(fridge.center.y, 0.85, accuracy: 1e-4)
        XCTAssertEqual(fridge.top_height, 1.7, accuracy: 1e-4)

        let sinkFindings = roomFindings.filter { $0.subjectID == "detector-sink" }
        XCTAssertFalse(sinkFindings.isEmpty, "the sink's own rules ran")
        let report = await engine.evaluateScan()
        XCTAssertTrue(report.findings.contains { $0.subjectID == "detector-sink" })
    }

    func testWithoutDetectorObjectsTheRoomIsUnchanged() async throws {
        let plain = try RustComplianceEngine(bundle: .main)
        let viaImport = try RustComplianceEngine(bundle: .main)
        let expected = try await plain.evaluateRoom(capturedRoomJSON: fixtureRoom())
        let actual = try await viaImport.evaluateRoom(capturedRoomJSON: fixtureRoom(), detectedObjects: [])
        XCTAssertEqual(actual, expected)
    }
}
