import XCTest
@testable import StandardPhysics

@MainActor
final class AppModelTests: XCTestCase {
    private final class RecordingProcessor: ScanProcessing {
        var routeWhileProcessing: AppRoute?
        var shouldFail = false
        weak var model: AppModel?

        func process(_ manifest: ScanManifest, onUpdate: @escaping (ProcessingUpdate) -> Void) async throws -> ScanReport {
            routeWhileProcessing = model?.route
            onUpdate(ProcessingUpdate(stage: .checking, fraction: 0.5))
            if shouldFail { throw URLError(.notConnectedToInternet) }
            return SampleData.report(for: manifest)
        }
    }

    private func makeModel(processor: RecordingProcessor = RecordingProcessor(), stored: [ScanManifest] = [SampleData.unfinishedManifest()]) -> (AppModel, PreviewCaptureController) {
        let capture = PreviewCaptureController(storedScans: stored)
        let model = AppModel(capture: capture, processor: processor, unfinishedScans: stored)
        processor.model = model
        return (model, capture)
    }

    func testStartingANewScanShowsTheBriefingFirst() async {
        let (model, capture) = makeModel()
        model.startNewScan()
        XCTAssertEqual(model.route, .beforeYouScan)
        await model.beginScanning(name: "  Corner Deli ")
        XCTAssertEqual(model.route, .capture)
        XCTAssertEqual(capture.phase, .scanning(room: 1))
        XCTAssertEqual(capture.manifest?.name, "Corner Deli")
    }

    func testContinuingAnUnfinishedScanGoesStraightToRelocalizing() async {
        let scan = SampleData.unfinishedManifest(roomsSaved: 2)
        let (model, capture) = makeModel(stored: [scan])
        await model.continueScan(scan.scanID)
        XCTAssertEqual(model.route, .capture)
        XCTAssertEqual(capture.phase, .relocalizing(room: 3))
    }

    func testFinishingGoesToProcessingThenResults() async throws {
        let processor = RecordingProcessor()
        let (model, capture) = makeModel(processor: processor)
        await model.beginScanning(name: "Corner Deli")
        await model.finishRoom()
        XCTAssertEqual(capture.phase, .betweenRooms(completed: 1))
        await model.nameRoom(index: 1, name: "Sales floor")
        await model.finishScan()

        XCTAssertEqual(processor.routeWhileProcessing, .processing)
        let scanID = try XCTUnwrap(capture.manifest?.scanID)
        XCTAssertEqual(model.route, .results(scanID))
        XCTAssertEqual(model.report(id: scanID)?.roomNames, ["Sales floor"])
        XCTAssertNil(model.processing)
    }

    func testAFailedCheckStaysOnProcessingWithAWayToRetry() async {
        let processor = RecordingProcessor()
        processor.shouldFail = true
        let (model, _) = makeModel(processor: processor)
        await model.beginScanning(name: "Corner Deli")
        await model.finishRoom()
        await model.finishScan()

        XCTAssertEqual(model.route, .processing)
        XCTAssertNotNil(model.processing?.failure)

        processor.shouldFail = false
        await model.retryProcessing()
        XCTAssertNotNil(model.reports.first)
        if case .results = model.route {} else { XCTFail("Expected results, got \(model.route)") }
    }

    func testFinishedScanLeavesTheUnfinishedList() async {
        let scan = SampleData.unfinishedManifest()
        let (model, _) = makeModel(stored: [scan])
        await model.continueScan(scan.scanID)
        await model.finishScan()
        XCTAssertFalse(model.unfinishedScans.contains { $0.scanID == scan.scanID })
    }

    func testAScanHoldsAtMostEightRooms() async {
        let full = SampleData.unfinishedManifest(roomsSaved: ScanLimits.maxRooms)
        let (model, capture) = makeModel(stored: [full])
        await model.continueScan(full.scanID)
        XCTAssertFalse(model.canAddRoom)
        model.scanAnotherRoom()
        XCTAssertEqual(capture.phase, .relocalizing(room: ScanLimits.maxRooms + 1))
    }

    func testLeavingMidScanKeepsItOnHome() async {
        let (model, _) = makeModel(stored: [])
        await model.beginScanning(name: "Corner Deli")
        await model.leaveCapture()
        XCTAssertEqual(model.route, .home)
        XCTAssertEqual(model.unfinishedScans.map(\.name), ["Corner Deli"])
    }

    func testFinishedReportsAreSavedAndComeBackAfterARelaunch() async throws {
        let root = FileManager.default.temporaryDirectory.appending(path: "app-reports-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let capture = PreviewCaptureController(storedScans: [])
        let model = AppModel(capture: capture, processor: RecordingProcessor(), reportStore: FileReportStore(root: root))
        await model.beginScanning(name: "Corner Deli")
        await model.finishRoom()
        await model.finishScan()
        let scanID = try XCTUnwrap(capture.manifest?.scanID)

        let relaunched = AppModel(capture: PreviewCaptureController(storedScans: []), processor: RecordingProcessor(), reportStore: FileReportStore(root: root))
        XCTAssertNil(relaunched.report(id: scanID))
        await relaunched.refresh()
        XCTAssertEqual(relaunched.report(id: scanID)?.name, "Corner Deli")
    }

    func testScreenLaunchArgumentStagesTheRightState() {
        let relocalizing = LaunchConfiguration.fromProcess(arguments: ["app", "-screen", "relocalizing"])
        XCTAssertEqual(relocalizing.model.route, .capture)
        XCTAssertEqual(relocalizing.model.capture.phase, .relocalizing(room: 3))
        let results = LaunchConfiguration.fromProcess(arguments: ["app", "-screen", "results"])
        XCTAssertEqual(results.model.route, .results(SampleData.completedReport.scanID))
        XCTAssertEqual(LaunchConfiguration.fromProcess(arguments: ["app"]).model.route, .home)
    }
}
