import XCTest
@testable import StandardPhysics

final class AskDecodingTests: XCTestCase {
    func testServerFindingsCarryTheirAsk() throws {
        let json = #"""
        {"rule_id":"ADA-309.4","jurisdiction":"ADA2010","section":"309.4","title":"Faucet","subject_id":"sink-1","room_id":null,
         "status":"needs_info","severity":"violation","measured":null,"required":"","message":"m","evidence":"owner","location":null,
         "counterpart":null,"ask":{"metric":"lavatory.faucet_lever_operable","prompt":"Can the faucet be worked with one closed fist?",
         "value_type":"boolean","unit":"","options":[],"photo":true}}
        """#
        let finding = try WireCoding.decoder().decode(ServerFinding.self, from: Data(json.utf8))
        let ask = try XCTUnwrap(finding.asFinding?.ask)
        XCTAssertEqual(ask.metric, "lavatory.faucet_lever_operable")
        XCTAssertEqual(ask.valueType, .boolean)
        XCTAssertTrue(ask.photo)
    }

    func testANullOrMissingAskDecodesAsNone() throws {
        let json = #"{"rule_id":"r","jurisdiction":"ADA2010","section":"404","subject_id":"d","status":"fail","measured":null,"required":"","message":"m","ask":null}"#
        XCTAssertNil(try JSONDecoder().decode(Finding.self, from: Data(json.utf8)).ask)
    }

    func testEnumAsksKeepTheirOptionsAndUnknownTypesAreUnsupported() throws {
        let choice = #"{"metric":"site.use","prompt":"What kind of business?","value_type":"enum","options":["retail","restaurant"]}"#
        let decoded = try JSONDecoder().decode(FindingAsk.self, from: Data(choice.utf8))
        XCTAssertEqual(decoded.valueType, .choice)
        XCTAssertEqual(decoded.options, ["retail", "restaurant"])
        XCTAssertEqual(decoded.unit, "")
        XCTAssertFalse(decoded.photo)

        let future = #"{"metric":"m","prompt":"p","value_type":"colour"}"#
        XCTAssertEqual(try JSONDecoder().decode(FindingAsk.self, from: Data(future.utf8)).valueType, .unsupported)
    }

    func testFindingsKeepTheirAskThroughARoundTrip() throws {
        let finding = Finding(
            ruleID: "r", jurisdiction: .ada2010, section: "404.2.9", subjectID: "door-1", status: .needsInfo, measured: nil,
            required: "", message: "m", ask: LibraryFixtures.ask
        )
        XCTAssertEqual(try JSONDecoder().decode(Finding.self, from: JSONEncoder().encode(finding)), finding)
    }
}

final class OwnerQuestionsTests: XCTestCase {
    private func question(_ section: String, jurisdiction: Jurisdiction, ask: FindingAsk?, subject: String = "door-1") -> Finding {
        Finding(
            ruleID: "\(jurisdiction.rawValue)-\(section)", jurisdiction: jurisdiction, section: section, subjectID: subject,
            status: .needsInfo, measured: nil, required: "", message: "m", ask: ask
        )
    }

    func testTwinsAndSectionsSharingAMetricAreAskedOnce() {
        let findings = [
            question("404.2.9", jurisdiction: .ada2010, ask: LibraryFixtures.ask),
            question("11B-404.2.9", jurisdiction: .cbc11b, ask: LibraryFixtures.ask),
            question("11B-404.2.9.1", jurisdiction: .cbc11b, ask: LibraryFixtures.ask),
            question("404.2.9", jurisdiction: .ada2010, ask: LibraryFixtures.ask, subject: "door-2"),
            question("703.4.1", jurisdiction: .ada2010, ask: nil),
        ]
        let outcomes = RuleComparison.outcomes(from: findings)
        XCTAssertEqual(outcomes.count, 4)
        let asked = OwnerQuestions.deduplicated(outcomes)
        XCTAssertEqual(asked.compactMap { OwnerQuestions.question(for: $0)?.id }, ["door-1#door.opening_force", "door-2#door.opening_force"])
        XCTAssertEqual(asked.count, 3, "the question with no ask still shows")

        let report = ScanReport(scanID: UUID(), name: "x", completedAt: fixedNow, roomNames: [], subjects: [:], findings: findings)
        XCTAssertEqual(ReportGrouping.summary(for: report).questions, 3)
    }

    func testSettledFindingsAskNothing() {
        var settled = question("404.2.9", jurisdiction: .ada2010, ask: LibraryFixtures.ask)
        settled = Finding(
            ruleID: settled.ruleID, jurisdiction: .ada2010, section: "404.2.9", subjectID: "door-1", status: .pass,
            measured: nil, required: "", message: "m", ask: LibraryFixtures.ask
        )
        XCTAssertNil(RuleComparison.outcomes(from: [settled]).first.flatMap(OwnerQuestions.question(for:)))
    }

    func testSettingReplacesAndClearingRemoves() {
        let question = OwnerQuestion(subjectID: "door-1", ask: LibraryFixtures.ask)
        let first = OwnerQuestions.setting(.number(6), for: question, in: [])
        XCTAssertEqual(first, [OwnerAnswer(subjectID: "door-1", metric: "door.opening_force", value: .number(6), unit: "lbf")])
        let second = OwnerQuestions.setting(.number(4.5), for: question, in: first)
        XCTAssertEqual(second.map(\.value), [.number(4.5)])
        XCTAssertEqual(OwnerQuestions.answer(to: question, in: second)?.value, .number(4.5))
        XCTAssertTrue(OwnerQuestions.setting(nil, for: question, in: second).isEmpty)
    }

    func testClearingSendsANullSoTheServerForgetsIt() throws {
        let kept = OwnerAnswer(subjectID: "sink-1", metric: "lavatory.faucet_operable", value: .bool(true))
        let cleared = OwnerQuestion(subjectID: "door-1", ask: LibraryFixtures.ask)
        let updates = OwnerQuestions.updates(for: [kept], clearing: cleared)
        let body = try WireCoding.encoder().encode(AnswersRequest(answers: updates))
        XCTAssertEqual(
            String(data: body, encoding: .utf8),
            #"{"answers":[{"metric":"lavatory.faucet_operable","subject_id":"sink-1","value":true},{"metric":"door.opening_force","subject_id":"door-1","value":null}]}"#
        )
    }

    func testAnswerValuesKeepTheirJSONShape() throws {
        let values: [AnswerValue] = [.bool(false), .number(42), .text("retail")]
        let encoded = try JSONEncoder().encode(values)
        XCTAssertEqual(String(data: encoded, encoding: .utf8), #"[false,42,"retail"]"#)
        XCTAssertEqual(try JSONDecoder().decode([AnswerValue].self, from: encoded), values)
    }

    func testNumbersAcceptCommasAndIntegersRound() {
        XCTAssertEqual(OwnerQuestions.numberValue(from: " 4,5 ", valueType: .number), .number(4.5))
        XCTAssertEqual(OwnerQuestions.numberValue(from: "2.6", valueType: .integer), .number(3))
        XCTAssertNil(OwnerQuestions.numberValue(from: "five", valueType: .number))
        XCTAssertNil(OwnerQuestions.numberValue(from: "", valueType: .number))
    }

    func testWords() {
        XCTAssertEqual(OwnerQuestions.optionTitle("full_service"), "Full service")
        XCTAssertEqual(OwnerQuestions.unitName("lbf"), "pounds of force")
        XCTAssertEqual(OwnerQuestions.text(for: .number(5)), "5")
        XCTAssertEqual(OwnerQuestions.text(for: nil), "")
    }

    func testAServerRecheckKeepsTheOwnersNameAndAnswers() {
        var existing = ServerReports.scanReport(scan: LibraryFixtures.scan(), report: LibraryFixtures.report(), sceneJSON: nil)
        existing.name = "Deli, front"
        existing.answers = [OwnerAnswer(subjectID: "door-1", metric: "door.opening_force", value: .number(4))]
        let updated = ServerReports.updating(existing, with: LibraryFixtures.report(status: .pass))
        XCTAssertEqual(updated.name, "Deli, front")
        XCTAssertEqual(updated.answers, existing.answers)
        XCTAssertEqual(updated.findings.map(\.status), [.pass])
    }

    func testAnswerRoutes() {
        let save = APIRoutes.saveAnswers(scanID: "s1", body: AnswersRequest(answers: []))
        XCTAssertEqual(save.method, .put)
        XCTAssertEqual(save.path, "/v1/scans/s1/answers")
        XCTAssertTrue(save.isIdempotent)
        XCTAssertEqual(APIRoutes.answers(scanID: "s1").method, .get)
    }
}

@MainActor
final class OwnerAnswerFlowTests: XCTestCase {
    private final class RecordingRecheck: ReportRechecking {
        var calls: [[OwnerAnswer]] = []

        func recheck(scanID: UUID, answers: [OwnerAnswer]) async throws -> ScanReport {
            calls.append(answers)
            var report = SampleData.completedReport
            report.findings = []
            return report
        }
    }

    func testAnsweringAServerScanSendsItAndShowsTheNewReport() async throws {
        let library = FakeScanLibrary()
        let account = AccountModel(service: nil, state: .signedIn(email: "a@b.co"))
        let report = ServerReports.scanReport(scan: LibraryFixtures.scan(), report: LibraryFixtures.report(), sceneJSON: nil)
        let model = AppModel(capture: PreviewCaptureController(storedScans: []), processor: PreviewScanProcessor(), account: account, library: library, reports: [report])
        let question = OwnerQuestion(subjectID: "door-1", ask: LibraryFixtures.ask)

        await model.answer(question, with: .number(6), inReport: report.scanID)

        XCTAssertEqual(library.savedAnswers.first?.map(\.value), [.number(6)])
        XCTAssertEqual(model.report(id: report.scanID)?.findings.map(\.status), [.pass])
        XCTAssertEqual(model.answer(to: question, inReport: report.scanID), .number(6))
        XCTAssertNil(model.notice)
    }

    func testAnAnswerTheServerMissedStaysOnThePhone() async {
        let library = FakeScanLibrary()
        library.failNextCalls(with: .offline)
        let report = ServerReports.scanReport(scan: LibraryFixtures.scan(), report: LibraryFixtures.report(), sceneJSON: nil)
        let model = AppModel(capture: PreviewCaptureController(storedScans: []), processor: PreviewScanProcessor(), library: library, reports: [report])
        let question = OwnerQuestion(subjectID: "door-1", ask: LibraryFixtures.ask)

        await model.answer(question, with: .number(6), inReport: report.scanID)

        XCTAssertEqual(model.answer(to: question, inReport: report.scanID), .number(6))
        XCTAssertEqual(model.report(id: report.scanID)?.findings.map(\.status), [.needsInfo])
        XCTAssertEqual(model.notice, AppModel.answerNotSent)
    }

    func testAnsweringAPhoneReportChecksItAgainOnThePhone() async {
        let recheck = RecordingRecheck()
        let model = AppModel(capture: PreviewCaptureController(storedScans: []), processor: PreviewScanProcessor(), recheck: recheck, reports: [SampleData.completedReport])
        let question = OwnerQuestion(subjectID: "door-restroom", ask: FindingAsk(metric: "sign.braille_present", prompt: "p", valueType: .boolean))

        await model.answer(question, with: .bool(true), inReport: SampleData.completedReport.scanID)

        XCTAssertEqual(recheck.calls.first?.map(\.value), [.bool(true)])
        XCTAssertEqual(model.report(id: SampleData.completedReport.scanID)?.findings, [])
        XCTAssertEqual(model.report(id: SampleData.completedReport.scanID)?.name, SampleData.completedReport.name)
    }
}
