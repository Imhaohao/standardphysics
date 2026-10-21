import XCTest
@testable import StandardPhysics

final class WebLinksTests: XCTestCase {
    func testAnEmptyOrInsecureBaseHidesLinks() {
        XCTAssertNil(WebLinks.baseURL(from: nil))
        XCTAssertNil(WebLinks.baseURL(from: "  "))
        XCTAssertNil(WebLinks.baseURL(from: "http://standardphysics.app"))
        XCTAssertEqual(WebLinks.baseURL(from: "https://standardphysics.app"), URL(string: "https://standardphysics.app"))
    }

    func testLinksJoinTheBaseAndToken() {
        let base = URL(string: "https://standardphysics.app/")!
        XCTAssertEqual(WebLinks.sharedReportURL(base: base, token: "Ab_9-z"), URL(string: "https://standardphysics.app/r/Ab_9-z"))
        XCTAssertEqual(
            WebLinks.sharedReportURL(base: URL(string: "https://example.com/app")!, token: "t1"),
            URL(string: "https://example.com/app/r/t1")
        )
    }

    func testTokensThatArentURLSafeAreRefused() {
        let base = URL(string: "https://standardphysics.app")!
        XCTAssertNil(WebLinks.sharedReportURL(base: base, token: "../admin"))
        XCTAssertNil(WebLinks.sharedReportURL(base: base, token: ""))
        XCTAssertNil(WebLinks.sharedReportURL(base: base, token: "tök"))
    }

    func testShareRoute() {
        let route = APIRoutes.createShare(scanID: "s1")
        XCTAssertEqual(route.method, .post)
        XCTAssertEqual(route.path, "/v1/scans/s1/shares")
        XCTAssertFalse(route.isIdempotent)
    }
}

final class ReportOutlineTests: XCTestCase {
    func testTheOutlineFollowsTheScreen() {
        let lines = ReportOutline.lines(for: SampleData.completedReport)
        XCTAssertEqual(lines.first, ReportLine(style: .title, text: "Hollis Street Bakery"))
        XCTAssertEqual(lines.filter { $0.style == .room }.map(\.text), [SampleData.salesFloor, SampleData.restroom])
        XCTAssertTrue(lines.contains { $0.text.hasPrefix("To fix: Sales counter height") })
        XCTAssertTrue(lines.contains { $0.text.contains("CBC 11B-904.4.1") })
        XCTAssertTrue(lines.contains { $0.text.hasPrefix("Question: ") })
    }

    func testAnswersArePrinted() {
        var report = SampleData.completedReport
        report.answers = [OwnerAnswer(subjectID: "door-restroom", metric: "door.opening_force", value: .number(6), unit: "lbf")]
        XCTAssertTrue(ReportOutline.lines(for: report).contains { $0.text.contains("your answer 6 lbf") })
        XCTAssertEqual(ReportOutline.answerText(OwnerAnswer(subjectID: "s", metric: "m", value: .bool(true))), "yes")
    }

    func testFileNamesAreSafe() {
        var report = SampleData.completedReport
        report.name = "Joe's / Deli"
        XCTAssertEqual(ReportPDF.fileName(for: report), "Joe-s - Deli accessibility report.pdf")
    }
}

@MainActor
final class ReportPDFTests: XCTestCase {
    func testTheReportRendersAsAPDF() throws {
        let data = ReportPDF.data(for: SampleData.completedReport)
        XCTAssertEqual(String(data: data.prefix(4), encoding: .ascii), "%PDF")
        let url = try ReportPDF.write(SampleData.completedReport)
        XCTAssertEqual(url.pathExtension, "pdf")
        XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
    }

    func testLinksAreOfferedOnlyForSignedInServerScans() async {
        let library = FakeScanLibrary()
        let account = AccountModel(service: nil, state: .signedIn(email: "a@b.co"))
        let server = ServerReports.scanReport(scan: LibraryFixtures.scan(), report: LibraryFixtures.report(), sceneJSON: nil)
        let model = AppModel(
            capture: PreviewCaptureController(storedScans: []), processor: PreviewScanProcessor(), account: account,
            library: library, webBaseURL: URL(string: "https://standardphysics.app"), reports: [server, SampleData.completedReport]
        )
        XCTAssertTrue(model.canShareLink(for: server))
        XCTAssertFalse(model.canShareLink(for: SampleData.completedReport))
        let link = await model.makeShareLink(for: server.scanID)
        XCTAssertEqual(link, URL(string: "https://standardphysics.app/r/tok_6f1c"))

        let withoutWeb = AppModel(capture: PreviewCaptureController(storedScans: []), processor: PreviewScanProcessor(), account: account, library: library, reports: [server])
        XCTAssertFalse(withoutWeb.canShareLink(for: server))
    }
}
