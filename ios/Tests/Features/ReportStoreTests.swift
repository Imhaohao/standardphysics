import XCTest
@testable import StandardPhysics

final class FileReportStoreTests: XCTestCase {
    private var root: URL!

    override func setUp() async throws {
        root = FileManager.default.temporaryDirectory.appending(path: "reports-\(UUID().uuidString)")
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: root)
    }

    func testSavedReportsComeBackNewestFirst() async throws {
        let store = FileReportStore(root: root)
        var older = SampleData.earlierReport
        older.remoteScanID = "server-1"
        try await store.save(older)
        try await store.save(SampleData.completedReport)

        let reopened = FileReportStore(root: root)
        let loaded = await reopened.loadAll()
        XCTAssertEqual(loaded, [SampleData.completedReport, older])
    }

    func testSavingAgainReplacesTheReport() async throws {
        let store = FileReportStore(root: root)
        var report = SampleData.completedReport
        try await store.save(report)
        report.name = "Hollis Street Bakery, upstairs"
        try await store.save(report)

        let loaded = await store.loadAll()
        XCTAssertEqual(loaded.map(\.name), ["Hollis Street Bakery, upstairs"])
    }

    func testDeletedReportsStayGone() async throws {
        let store = FileReportStore(root: root)
        try await store.save(SampleData.completedReport)
        try await store.delete(scanID: SampleData.completedReport.scanID)
        try await store.delete(scanID: SampleData.completedReport.scanID)
        let loaded = await store.loadAll()
        XCTAssertTrue(loaded.isEmpty)
    }

    func testUnreadableFilesAreSkipped() async throws {
        let store = FileReportStore(root: root)
        try await store.save(SampleData.completedReport)
        try Data("not json".utf8).write(to: root.appending(path: "\(UUID().uuidString).json"))
        let loaded = await store.loadAll()
        XCTAssertEqual(loaded.map(\.scanID), [SampleData.completedReport.scanID])
    }

    func testReportsSavedWithoutTheServerIDStillDecode() throws {
        let json = #"{"scanID":"0B7E4D21-3A9F-4B6C-8E15-2C4D6F8A9B30","name":"Juniper Books","completedAt":0,"roomNames":["Sales floor"],"subjects":{},"findings":[]}"#
        let decoded = try JSONDecoder().decode(ScanReport.self, from: Data(json.utf8))
        XCTAssertEqual(decoded.name, "Juniper Books")
        XCTAssertNil(decoded.remoteScanID)
    }
}

final class ReportSyncTests: XCTestCase {
    private func scan(_ id: String, name: String = "Cafe", status: String = "complete") -> ScanResponse {
        ScanResponse(id: id, name: name, siteName: nil, status: status, createdAt: fixedNow, updatedAt: fixedNow)
    }

    private func report(remote: String?, name: String = "Cafe") -> ScanReport {
        ScanReport(scanID: UUID(), name: name, completedAt: fixedNow, roomNames: [], subjects: [:], findings: [], remoteScanID: remote)
    }

    func testOnlyCheckedScansMissingHereAreFetched() {
        let held = report(remote: "s1")
        let plan = ReportSync.plan(local: [held], server: [scan("s1"), scan("s2"), scan("s3", status: "capturing")])
        XCTAssertEqual(plan.toFetch.map(\.id), ["s2"])
        XCTAssertEqual(plan.kept, [held])
    }

    func testServerNamesWinAndDeletedScansLeave() {
        let renamed = report(remote: "s1", name: "Old name")
        let deleted = report(remote: "gone")
        let local = report(remote: nil)
        let plan = ReportSync.plan(local: [renamed, deleted, local], server: [scan("s1", name: "New name")])
        XCTAssertEqual(plan.kept.map(\.name), ["New name", "Cafe"])
        XCTAssertEqual(plan.kept.last, local, "a report checked on this phone is never removed")
    }

    func testAServerOnlyScanIsNamedFromItsScene() {
        let scene = #"{"rooms":[{"id":"room-a","name":"Dining room","objects":[{"id":"sink-1","category":"lavatory"}],"openings":[],"walls":[]}]}"#
        let sink = ServerFindingFixture.make(ruleID: "ADA-606", subjectID: "sink-1")
        let stray = ServerFindingFixture.make(ruleID: "ADA-404", subjectID: "door-9")
        let serverReport = Report(
            scanID: "6f1c3a52-0000-4000-8000-000000000001", assessmentID: "a1", createdAt: fixedNow,
            summary: ServerFindingFixture.summary, findings: [sink, stray], timings: StageTimings(loadMs: 0, labellingMs: 0, evaluationMs: 0, persistMs: 0, totalMs: 0),
            labelledByVision: 0, unlabelledObjects: 0
        )
        let built = ServerReports.scanReport(scan: scan("6f1c3a52-0000-4000-8000-000000000001", name: "Juniper"), report: serverReport, sceneJSON: scene)

        XCTAssertEqual(built.scanID, UUID(uuidString: "6f1c3a52-0000-4000-8000-000000000001"))
        XCTAssertEqual(built.remoteScanID, "6f1c3a52-0000-4000-8000-000000000001")
        XCTAssertEqual(built.name, "Juniper")
        XCTAssertEqual(built.roomNames, ["Dining room"])
        XCTAssertEqual(built.subjects["sink-1"]?.label, "Lavatory")
        XCTAssertEqual(built.subjects["door-9"]?.label, "Door clear width")
        XCTAssertEqual(built.findings.count, 2)
    }
}

final class LibraryRouteTests: XCTestCase {
    func testScanLibraryPaths() {
        XCTAssertEqual(APIRoutes.listScans().path, "/v1/scans")
        XCTAssertEqual(APIRoutes.listScans().method, .get)
        XCTAssertEqual(APIRoutes.scene(scanID: "s1").path, "/v1/scans/s1/scene")
    }

    func testListingScansDecodesTheServerList() async throws {
        let json = #"[{"id":"s1","name":"Cafe","site_name":null,"status":"complete","created_at":"2026-10-19T10:00:00Z","updated_at":"2026-10-19T10:00:00Z"}]"#
        let transport = ScriptedTransport([jsonResponse(200, json)])
        let client = APIClient(baseURL: URL(string: "https://api.test")!, tokenStore: InMemoryTokenStore(token: "t"), transport: transport)
        let scans = try await client.listScans()
        XCTAssertEqual(scans.map(\.status), ["complete"])
        XCTAssertEqual(transport.requests.first?.url?.path, "/v1/scans")
    }
}
