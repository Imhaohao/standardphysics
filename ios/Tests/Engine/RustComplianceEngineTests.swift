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
            required: ">= 32 in", message: "Too narrow", evidence: "measured", severity: "violation", location: nil
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
            measured: nil, required: "", message: "m", evidence: "", severity: "info", location: nil
        )
        let finding = Finding(source)
        XCTAssertEqual(finding.jurisdiction, .system)
        XCTAssertNil(finding.title)
        XCTAssertEqual(finding.severity, .info)
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
}
