import XCTest
@testable import StandardPhysics

final class FindingCodingTests: XCTestCase {
    func testOlderFindingsWithoutTheNewFieldsStillDecode() throws {
        let json = #"{"rule_id":"r","jurisdiction":"ADA2010","section":"404","subject_id":"d","status":"fail","measured":null,"required":"","message":"m"}"#
        let finding = try JSONDecoder().decode(Finding.self, from: Data(json.utf8))
        XCTAssertNil(finding.title)
        XCTAssertNil(finding.severity)
        XCTAssertNil(finding.counterpartRuleID)
        XCTAssertNil(finding.range)
    }

    func testSystemFindingsAndUnknownSeveritiesDecode() throws {
        let json = #"{"rule_id":"label.unresolved","jurisdiction":"SYSTEM","section":"","subject_id":"o","status":"needs_info","measured":null,"required":"","message":"m","title":"Object not identified","severity":"critical-ish"}"#
        let finding = try JSONDecoder().decode(Finding.self, from: Data(json.utf8))
        XCTAssertEqual(finding.jurisdiction, .system)
        XCTAssertNil(finding.severity, "an unknown severity must not fail the report")
        XCTAssertEqual(finding.title, "Object not identified")
    }

    func testRoundTripKeepsEveryField() throws {
        let finding = Finding(
            ruleID: "r", jurisdiction: .cbc11b, section: "11B-404", subjectID: "d", status: .fail,
            measured: MeasuredValue(value: 0.7, unit: "m"), required: ">= 0.815 m", message: "m", title: "Door width",
            severity: .advisory, counterpartRuleID: "ADA-404", range: MeasuredRange(lo: 0.69, hi: 0.72, unit: "m")
        )
        let decoded = try JSONDecoder().decode(Finding.self, from: JSONEncoder().encode(finding))
        XCTAssertEqual(decoded, finding)
    }

    func testServerFindingKeepsTitleSeverityCounterpartAndRange() {
        let server = ServerFinding(
            ruleID: "ADA-404", jurisdiction: "ADA2010", section: "404", title: "Door clear width", subjectID: "d", roomID: nil,
            status: .fail, severity: "violation",
            measured: ServerMeasured(text: "0.7 to 0.72 m", value: nil, lo: 0.7, hi: 0.72, unit: "m"),
            required: ">= 0.815 m", message: "Too narrow", evidence: "measured", location: nil, counterpart: "CBC-404"
        )
        let finding = server.asFinding
        XCTAssertEqual(finding?.title, "Door clear width")
        XCTAssertEqual(finding?.severity, .violation)
        XCTAssertEqual(finding?.counterpartRuleID, "CBC-404")
        XCTAssertEqual(finding?.range, MeasuredRange(lo: 0.7, hi: 0.72, unit: "m"))
        XCTAssertEqual(finding?.measured, MeasuredValue(value: 0.7, unit: "m"))
    }

    func testServerSystemFindingsMapAndUnknownJurisdictionsDoNot() {
        let system = ServerFindingFixture.make(ruleID: "label.unresolved", subjectID: "o", jurisdiction: "SYSTEM", status: .needsInfo)
        XCTAssertEqual(system.asFinding?.jurisdiction, .system)
        XCTAssertNil(ServerFindingFixture.make(ruleID: "x", subjectID: "o", jurisdiction: "NYC").asFinding)
    }
}
