import XCTest
@testable import StandardPhysics

final class ReportGroupingTests: XCTestCase {
    private func finding(_ jurisdiction: Jurisdiction, _ section: String, status: FindingStatus, required: String, subject: String = "counter-1") -> Finding {
        Finding(ruleID: "\(jurisdiction.rawValue)-\(section)", jurisdiction: jurisdiction, section: section, subjectID: subject, status: status, measured: MeasuredValue(value: 35.5, unit: "in"), required: required, message: "")
    }

    func testCaliforniaGovernsWhenItFailsAndFederalPasses() {
        let federal = finding(.ada2010, "904.4.1", status: .pass, required: "≤ 36 in")
        let california = finding(.cbc11b, "11B-904.4.1", status: .fail, required: "≤ 34 in")
        let outcomes = RuleComparison.outcomes(from: [federal, california])
        XCTAssertEqual(outcomes.count, 1)
        XCTAssertEqual(outcomes[0].governing, california)
        XCTAssertEqual(outcomes[0].status, .fail)
        XCTAssertTrue(outcomes[0].hasBothJurisdictions)
    }

    func testFederalGovernsWhenOnlyFederalFails() {
        let federal = finding(.ada2010, "404.2.3", status: .fail, required: "≥ 32 in")
        let california = finding(.cbc11b, "11B-404.2.3", status: .needsInfo, required: "≥ 32 in")
        XCTAssertEqual(RuleComparison.governing(federal: federal, california: california), federal)
    }

    func testTighterLimitGovernsWhenResultsMatch() {
        let federal = finding(.ada2010, "x", status: .pass, required: "≤ 30 in")
        let california = finding(.cbc11b, "11B-x", status: .pass, required: "≤ 34 in")
        XCTAssertEqual(RuleComparison.governing(federal: federal, california: california), federal)

        let federalRange = finding(.ada2010, "604.2", status: .fail, required: "16–18 in")
        let californiaRange = finding(.cbc11b, "11B-604.2", status: .fail, required: "17–18 in")
        XCTAssertEqual(RuleComparison.governing(federal: federalRange, california: californiaRange), californiaRange)
    }

    func testCaliforniaGovernsATie() {
        let federal = finding(.ada2010, "404.2.3", status: .fail, required: "≥ 32 in")
        let california = finding(.cbc11b, "11B-404.2.3", status: .fail, required: "≥ 32 in")
        XCTAssertEqual(RuleComparison.governing(federal: federal, california: california), california)
    }

    func testASingleJurisdictionGovernsAlone() {
        let federal = finding(.ada2010, "308.2.1", status: .pass, required: "≤ 48 in")
        let outcome = RuleComparison.outcomes(from: [federal])[0]
        XCTAssertEqual(outcome.governing, federal)
        XCTAssertFalse(outcome.hasBothJurisdictions)
    }

    func testRequiredBoundParsing() {
        XCTAssertEqual(RequiredBound.parse("≤ 34 in"), .atMost(34))
        XCTAssertEqual(RequiredBound.parse("<= 34in"), .atMost(34))
        XCTAssertEqual(RequiredBound.parse("at least 32 in"), .atLeast(32))
        XCTAssertEqual(RequiredBound.parse("17–18 in"), .between(17, 18))
        XCTAssertEqual(RequiredBound.parse("18 to 17"), .between(17, 18))
        XCTAssertNil(RequiredBound.parse("Yes"))
        XCTAssertTrue(RequiredBound.between(17, 18).isStricter(than: .between(16, 18)))
        XCTAssertFalse(RequiredBound.atMost(34).isStricter(than: .atLeast(10)))
    }

    func testSampleReportGroupsByRoomThenObject() {
        let sections = ReportGrouping.sections(for: SampleData.completedReport)
        XCTAssertEqual(sections.map(\.name), [SampleData.salesFloor, SampleData.restroom])

        let restroom = sections[1]
        let door = restroom.objects.first { $0.subject.id == "door-restroom" }
        XCTAssertEqual(door?.outcomes.count, 4)
        XCTAssertEqual(door?.issues.map(\.status), [.fail, .needsInfo, .needsInfo, .needsInfo])
        XCTAssertEqual(restroom.objects.first?.worstSeverity, FindingStatus.fail.severity)
        XCTAssertEqual(restroom.passing.map(\.subject.label).sorted(), ["Rear grab bar", "Sink"])
    }

    func testOwnerChecksAreQuestionsNeverViolations() {
        let check = Finding(
            ruleID: "label.unresolved", jurisdiction: .system, section: "", subjectID: "obj", status: .fail,
            measured: nil, required: "", message: "Check this object", title: "Object not identified"
        )
        let outcomes = RuleComparison.outcomes(from: [check])
        XCTAssertEqual(outcomes.count, 1)
        XCTAssertTrue(outcomes[0].isOwnerQuestion)
        XCTAssertNil(outcomes[0].federal)
        XCTAssertNil(outcomes[0].california)
        let report = ScanReport(scanID: UUID(), name: "x", completedAt: .now, roomNames: [], subjects: [:], findings: [check])
        XCTAssertEqual(ReportGrouping.summary(for: report), ReportSummary(toFix: 0, questions: 1, passing: 0))
        XCTAssertEqual(ReportGrouping.sections(for: report).first?.objectsWithIssues.count, 1)
        XCTAssertEqual(Citation.jurisdictionName(.system), "Standard Physics")
    }

    func testOwnerChecksDoNotPairWithCodeFindingsOnTheSameSubject() {
        let code = Finding(ruleID: "ADA-1", jurisdiction: .ada2010, section: "", subjectID: "obj", status: .pass, measured: nil, required: "", message: "ok")
        let check = Finding(ruleID: "label.unresolved", jurisdiction: .system, section: "", subjectID: "obj", status: .needsInfo, measured: nil, required: "", message: "?")
        let outcomes = RuleComparison.outcomes(from: [code, check])
        XCTAssertEqual(outcomes.map(\.governing.ruleID), ["ADA-1", "label.unresolved"])
    }

    func testSummaryCountsEachRequirementOnce() {
        XCTAssertEqual(ReportGrouping.summary(for: SampleData.completedReport), ReportSummary(toFix: 6, questions: 4, passing: 4))
    }

    func testUnknownSubjectsLandElsewhere() {
        let report = ScanReport(scanID: UUID(), name: "Test", completedAt: .now, roomNames: ["Lobby"], subjects: [:],
                                findings: [finding(.ada2010, "1", status: .fail, required: "≤ 1 in", subject: "mystery")])
        XCTAssertEqual(ReportGrouping.sections(for: report).map(\.name), [ReportGrouping.unassignedRoom])
    }

    func testCitations() {
        let federal = finding(.ada2010, "904.4.1", status: .pass, required: "")
        let california = finding(.cbc11b, "11B-904.4.1", status: .pass, required: "")
        let bareCalifornia = finding(.cbc11b, "904.4.1", status: .pass, required: "")
        XCTAssertEqual(Citation.text(for: federal), "ADA 2010 §904.4.1")
        XCTAssertEqual(Citation.text(for: california), "CBC 11B-904.4.1")
        XCTAssertEqual(Citation.text(for: bareCalifornia), "CBC 11B-904.4.1")
    }

    func testMeasurementsShowInInches() {
        XCTAssertEqual(MeasurementFormat.string(MeasuredValue(value: 0.8636, unit: "m")), "34 in")
        XCTAssertEqual(MeasurementFormat.string(MeasuredValue(value: 35.5, unit: "in")), "35.5 in")
        XCTAssertEqual(MeasurementFormat.string(MeasuredValue(value: 8.3, unit: "%")), "8.3%")
    }

    func testGaugeNamesTheGap() {
        XCTAssertEqual(GaugeGeometry(value: 35.5, bound: .atMost(34)).label(unit: "in"), "1.5 in over")
        XCTAssertEqual(GaugeGeometry(value: 12, bound: .atLeast(18)).label(unit: "in"), "6 in short")
        XCTAssertEqual(GaugeGeometry(value: 16.5, bound: .between(17, 18)).label(unit: "in"), "0.5 in short")
        XCTAssertNil(GaugeGeometry(value: 34, bound: .between(33, 36)).nearestLimit)
    }
}
