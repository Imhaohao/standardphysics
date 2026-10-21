import XCTest
@testable import StandardPhysics

@MainActor
final class ReportManagementTests: XCTestCase {
    private func serverReport() -> ScanReport {
        ServerReports.scanReport(scan: LibraryFixtures.scan(), report: LibraryFixtures.report(), sceneJSON: nil)
    }

    private func makeModel(library: FakeScanLibrary, reports: [ScanReport], unfinished: [ScanManifest] = []) -> AppModel {
        AppModel(
            capture: PreviewCaptureController(storedScans: unfinished), processor: PreviewScanProcessor(),
            library: library, unfinishedScans: unfinished, reports: reports
        )
    }

    func testDeletingAServerReportDeletesItOnTheAccountToo() async {
        let library = FakeScanLibrary()
        let report = serverReport()
        let model = makeModel(library: library, reports: [report, SampleData.earlierReport])
        model.openReport(report.scanID)

        await model.deleteReport(report.scanID)

        XCTAssertEqual(library.deleted, [LibraryFixtures.scanID])
        XCTAssertEqual(model.reports.map(\.scanID), [SampleData.earlierReport.scanID])
        XCTAssertEqual(model.route, .home)
    }

    func testAFailedServerDeleteKeepsTheReport() async {
        let library = FakeScanLibrary()
        library.failNextCalls(with: .offline)
        let report = serverReport()
        let model = makeModel(library: library, reports: [report])

        await model.deleteReport(report.scanID)

        XCTAssertNotNil(model.report(id: report.scanID))
        XCTAssertEqual(model.notice, AppModel.deleteNotSent)
    }

    func testAScanAlreadyGoneFromTheAccountStillLeavesThePhone() async {
        let library = FakeScanLibrary()
        library.failNextCalls(with: .notFound)
        let report = serverReport()
        let model = makeModel(library: library, reports: [report])

        await model.deleteReport(report.scanID)

        XCTAssertNil(model.report(id: report.scanID))
        XCTAssertNil(model.notice)
    }

    func testAPhoneReportIsDeletedWithoutTheServer() async {
        let library = FakeScanLibrary()
        let model = makeModel(library: library, reports: [SampleData.completedReport])
        await model.deleteReport(SampleData.completedReport.scanID)
        XCTAssertTrue(model.reports.isEmpty)
        XCTAssertTrue(library.deleted.isEmpty)
    }

    func testRenamingTrimsAndRenamesOnTheAccount() async {
        let library = FakeScanLibrary()
        let report = serverReport()
        let model = makeModel(library: library, reports: [report])

        await model.renameReport(report.scanID, to: "  Deli, back room ")
        await model.renameReport(report.scanID, to: "   ")

        XCTAssertEqual(library.renamed, [LibraryFixtures.scanID: "Deli, back room"])
        XCTAssertEqual(model.report(id: report.scanID)?.name, "Deli, back room")
    }

    func testAFailedRenameKeepsTheOldName() async {
        let library = FakeScanLibrary()
        library.failNextCalls(with: .timedOut)
        let report = serverReport()
        let model = makeModel(library: library, reports: [report])

        await model.renameReport(report.scanID, to: "New")

        XCTAssertEqual(model.report(id: report.scanID)?.name, report.name)
        XCTAssertEqual(model.notice, AppModel.renameNotSent)
    }

    func testDeletingAnUnfinishedScanRemovesItEverywhere() async {
        var scan = SampleData.unfinishedManifest()
        scan.remoteScanID = "server-scan"
        let library = FakeScanLibrary()
        let model = makeModel(library: library, reports: [], unfinished: [scan])

        await model.deleteUnfinishedScan(scan.scanID)

        XCTAssertTrue(model.unfinishedScans.isEmpty)
        XCTAssertEqual(library.deleted, ["server-scan"])
        await model.continueScan(scan.scanID)
        XCTAssertNotEqual(model.capture.manifest?.scanID, scan.scanID, "the saved scan is gone")
    }

    func testRenameAndDeleteRoutes() {
        let rename = APIRoutes.renameScan(scanID: "s1", body: RenameScanRequest(name: "x"))
        XCTAssertEqual(rename.method, .patch)
        XCTAssertEqual(rename.path, "/v1/scans/s1")
        let delete = APIRoutes.deleteScan(scanID: "s1")
        XCTAssertEqual(delete.method, .delete)
        XCTAssertEqual(delete.path, "/v1/scans/s1")
    }

    func testDeleteAcceptsAnEmptyNoContentResponse() async throws {
        let transport = ScriptedTransport([.success(HTTPResponse(status: 204, headers: [:], body: Data()))])
        let client = APIClient(baseURL: URL(string: "https://api.test")!, tokenStore: InMemoryTokenStore(token: "t"), transport: transport)
        try await client.deleteScan(scanID: "s1")
        XCTAssertEqual(transport.requests.first?.httpMethod, "DELETE")
    }
}
