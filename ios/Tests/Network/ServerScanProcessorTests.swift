import XCTest
@testable import StandardPhysics

@MainActor
final class ServerScanProcessorTests: XCTestCase {
    nonisolated(unsafe) private var directory: URL!

    override func setUp() async throws { directory = try makeTemporaryDirectory() }
    override func tearDown() async throws { try? FileManager.default.removeItem(at: directory) }

    private let reportJSON = """
    {"scan_id":"6f1c3a52-0000-4000-8000-000000000001","assessment_id":"a1","created_at":"2026-10-19T10:00:00Z",
     "labelled_by_vision":0,"unlabelled_objects":0,
     "timings":{"load_ms":1,"labelling_ms":0,"evaluation_ms":3,"persist_ms":1,"total_ms":5},
     "summary":{"total":{"pass":0,"fail":1,"needs_info":1,"not_applicable":0},"by_jurisdiction":{}},
     "findings":[
      {"rule_id":"ADA-404","jurisdiction":"ADA2010","section":"404","title":"Door clear width","subject_id":"door-1","room_id":"room-1",
       "status":"fail","severity":"high","measured":{"text":"0.7 m","value":0.7,"lo":null,"hi":null,"unit":"m"},"required":">= 0.815 m",
       "message":"Too narrow","evidence":"measured","location":null,"counterpart":null},
      {"rule_id":"label.unresolved","jurisdiction":"SYSTEM","section":"","title":"Unlabelled","subject_id":"obj-9","room_id":null,
       "status":"needs_info","severity":"low","measured":null,"required":"","message":"?","evidence":"","location":null,"counterpart":null}]}
    """

    private func manifest(remoteID: String? = "scan-9") -> ScanManifest {
        ScanManifest(
            scanID: UUID(), name: "Cafe", startedAt: fixedNow, phase: .finishing,
            rooms: [RoomRecord(index: 1, name: "Kitchen", capturedRoomFile: "room-1.json", completedAt: fixedNow)],
            remoteScanID: remoteID
        )
    }

    private func makeProcessor(_ script: [Result<HTTPResponse, Error>]) -> (ServerScanProcessor, ScriptedTransport) {
        let transport = ScriptedTransport(script)
        let api = APIClient(baseURL: URL(string: "https://api.test")!, tokenStore: InMemoryTokenStore(token: "t"), transport: transport, retryPolicy: .none)
        let storage = UploadStorage(root: directory.appendingPathComponent("uploads"))
        let uploader = BackgroundUploader(
            api: FakeUploadAPI(), ledger: UploadLedger(fileURL: storage.ledgerURL), session: FakeUploadSession(), storage: storage
        )
        return (ServerScanProcessor(api: api, uploader: uploader), transport)
    }

    func testFinishesScanAndMapsReportWithRoomNamesAndSharedFindings() async throws {
        let (processor, transport) = makeProcessor([jsonResponse(200, reportJSON)])
        var stages: [ProcessingStage] = []
        let report = try await processor.process(manifest()) { stages.append($0.stage) }

        XCTAssertEqual(transport.requests[0].url?.path, "/v1/scans/scan-9/finish")
        XCTAssertEqual(stages.last, .writing)
        XCTAssertTrue(stages.contains(.assembling))
        XCTAssertEqual(report.name, "Cafe")
        XCTAssertEqual(report.roomNames, ["Kitchen"])
        XCTAssertEqual(report.findings.map(\.ruleID), ["ADA-404", "label.unresolved"])
        XCTAssertEqual(report.findings.last?.jurisdiction, .system)
        XCTAssertTrue(report.findings.last?.isOwnerQuestion ?? false)
        XCTAssertEqual(report.findings.first?.title, "Door clear width")
        XCTAssertEqual(report.subject(for: "door-1").roomName, "Kitchen")
        XCTAssertEqual(report.subject(for: "door-1").label, "Door clear width")
    }

    func testFallsBackToStoredAssessmentWhenFinishConflicts() async throws {
        let conflict = jsonResponse(409, #"{"error":"conflict","message":"scan is already being finished"}"#)
        let (processor, transport) = makeProcessor([conflict, jsonResponse(200, reportJSON)])
        let report = try await processor.process(manifest()) { _ in }
        XCTAssertEqual(transport.requests.map { $0.url?.path }, ["/v1/scans/scan-9/finish", "/v1/scans/scan-9/assessment"])
        XCTAssertEqual(report.findings.count, 2)
    }

    func testRoomsThatNeverReachedTheServerStopTheFinish() async {
        let transport = ScriptedTransport([jsonResponse(200, reportJSON)])
        let api = APIClient(baseURL: URL(string: "https://api.test")!, tokenStore: InMemoryTokenStore(token: "t"), transport: transport, retryPolicy: .none)
        let storage = UploadStorage(root: directory.appendingPathComponent("uploads"))
        let uploader = BackgroundUploader(
            api: FakeUploadAPI(), ledger: UploadLedger(fileURL: storage.ledgerURL), session: FakeUploadSession(), storage: storage
        )
        let processor = ServerScanProcessor(api: api, uploader: uploader, rooms: UndeliverableRooms())
        do {
            _ = try await processor.process(manifest()) { _ in }
            XCTFail("expected failure")
        } catch {
            XCTAssertEqual(error as? ScanStreamingError, .roomsNotDelivered)
        }
        XCTAssertTrue(transport.requests.isEmpty, "finish is never called on a partial scan")
    }

    func testHeavyLocalFilesAreReleasedOnlyAfterTheServerFinishes() async throws {
        let transport = ScriptedTransport([jsonResponse(500, "{}"), jsonResponse(200, reportJSON)])
        let api = APIClient(baseURL: URL(string: "https://api.test")!, tokenStore: InMemoryTokenStore(token: "t"), transport: transport, retryPolicy: .none)
        let storage = UploadStorage(root: directory.appendingPathComponent("uploads"))
        let uploader = BackgroundUploader(
            api: FakeUploadAPI(), ledger: UploadLedger(fileURL: storage.ledgerURL), session: FakeUploadSession(), storage: storage
        )
        let retention = RecordingRetention()
        let processor = ServerScanProcessor(api: api, uploader: uploader, retention: retention)
        let scan = manifest()
        _ = try? await processor.process(scan) { _ in }
        XCTAssertTrue(retention.released.isEmpty, "a failed finish keeps everything for a retry")
        _ = try await processor.process(scan) { _ in }
        XCTAssertEqual(retention.released, [scan.scanID])
    }

    func testScanNeverRegisteredWithServerIsAnError() async {
        let (processor, _) = makeProcessor([])
        do {
            _ = try await processor.process(manifest(remoteID: nil)) { _ in }
            XCTFail("expected failure")
        } catch {
            XCTAssertEqual(error as? ScanProcessingError, .scanNotCreatedOnServer)
        }
    }
}

@MainActor
private final class UndeliverableRooms: RoomDelivering {
    func deliverRooms(of manifest: ScanManifest) async throws {
        throw ScanStreamingError.roomsNotDelivered
    }
}

private final class RecordingRetention: ScanRetaining, @unchecked Sendable {
    private let ids = Locked<[UUID]>([])
    var released: [UUID] { ids.read { $0 } }
    func releaseHeavyFiles(scanID: UUID) async throws { ids.write { $0.append(scanID) } }
}
