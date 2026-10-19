import XCTest
@testable import StandardPhysics

private final class FakeCreator: RemoteScanCreating, @unchecked Sendable {
    private let state = Locked<(keys: [String], errors: [APIError])>(([], []))
    var keys: [String] { state.read { $0.keys } }

    func fail(with errors: [APIError]) { state.write { $0.errors = errors } }

    func createScan(name: String?, siteName: String?, idempotencyKey: String) async throws -> ScanResponse {
        let error = state.write { state -> APIError? in
            state.keys.append(idempotencyKey)
            return state.errors.isEmpty ? nil : state.errors.removeFirst()
        }
        if let error { throw error }
        return ScanResponse(id: "remote-1", name: name ?? "", siteName: nil, status: "capturing", createdAt: fixedNow, updatedAt: fixedNow)
    }
}

private final class FakeFileUploader: ScanFileUploading, @unchecked Sendable {
    struct Call: Equatable { let file: String; let scanID: String; let kind: UploadKind }
    private let state = Locked<(calls: [Call], discards: [UploadKind])>(([], []))
    var calls: [Call] { state.read { $0.calls } }
    var discards: [UploadKind] { state.read { $0.discards } }

    func enqueue(fileURL: URL, scanID: String, kind: UploadKind, contentType: String) async throws -> UUID {
        state.write { $0.calls.append(Call(file: fileURL.lastPathComponent, scanID: scanID, kind: kind)) }
        return UUID()
    }

    func discardUnfinished(scanID: String, kind: UploadKind) async {
        state.write { $0.discards.append(kind) }
    }
}

private actor FakeChannel: LiveRoomChannel {
    nonisolated let messages: AsyncStream<LiveMessage>
    private let continuation: AsyncStream<LiveMessage>.Continuation
    private(set) var sent: [RoomUpdate] = []
    private(set) var opened = false
    private(set) var closed = false
    var answersRooms = true

    init() {
        (messages, continuation) = AsyncStream.makeStream(of: LiveMessage.self)
    }

    func open() { opened = true }
    func sendRoom(_ update: RoomUpdate) { sent.append(update) }
    var hasUnansweredRooms: Bool { !answersRooms && !sent.isEmpty }
    func close() { closed = true }
    func setAnswersRooms(_ value: Bool) { answersRooms = value }
    nonisolated func deliver(_ message: LiveMessage) { continuation.yield(message) }
}

@MainActor
private final class FakeLink: CaptureLinking {
    var createKeys: [String] = []
    var remoteIDs: [String] = []
    var merged: [[Finding]] = []

    func recordRemoteCreateKey(_ key: String, forScan scanID: UUID) async { createKeys.append(key) }
    func recordRemoteScanID(_ remoteScanID: String, forScan scanID: UUID) async { remoteIDs.append(remoteScanID) }
    func mergeServerFindings(_ findings: [Finding]) { merged.append(findings) }
}

@MainActor
final class ScanStreamerTests: XCTestCase {
    private var directory: URL!
    private var creator: FakeCreator!
    private var uploader: FakeFileUploader!
    private var channels: [FakeChannel] = []
    private var signedIn = true
    private var link: FakeLink!

    override func setUp() async throws {
        directory = try makeTemporaryDirectory()
        creator = FakeCreator()
        uploader = FakeFileUploader()
        channels = []
        signedIn = true
        link = FakeLink()
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: directory)
    }

    private func makeStreamer() -> ScanStreamer {
        ScanStreamer(dependencies: ScanStreamer.Dependencies(
            creator: creator,
            uploader: uploader,
            makeChannel: { [unowned self] _ in
                let channel = FakeChannel()
                channels.append(channel)
                return channel
            },
            isSignedIn: { [unowned self] in signedIn },
            directory: { [unowned self] _ in directory },
            createRetryDelay: .zero,
            deliveryTimeout: .milliseconds(300),
            sleep: { _ in await Task.yield() }
        ))
    }

    private func manifest(rooms: Int = 0, remoteID: String? = nil, createKey: String? = nil) throws -> ScanManifest {
        let records = try (0..<rooms).map { index -> RoomRecord in
            let file = "room-\(index).json"
            try Data(#"{"walls":[],"index":\#(index)}"#.utf8).write(to: directory.appending(path: file))
            return RoomRecord(index: index, name: "Room \(index + 1)", capturedRoomFile: file, completedAt: fixedNow)
        }
        try Data([1, 2, 3]).write(to: directory.appending(path: "mesh.spm"))
        return ScanManifest(
            scanID: UUID(), name: "Cafe", startedAt: fixedNow, phase: .scanning(room: rooms), rooms: records,
            meshFile: "mesh.spm", remoteScanID: remoteID, remoteCreateKey: createKey
        )
    }

    func testStartPersistsTheKeyBeforeCreatingThenRecordsTheRemoteID() async throws {
        let streamer = makeStreamer()
        streamer.capture(link, reached: .started(try manifest()))
        await streamer.settle()
        XCTAssertEqual(link.createKeys.count, 1)
        XCTAssertEqual(creator.keys, link.createKeys)
        XCTAssertEqual(link.remoteIDs, ["remote-1"])
        XCTAssertEqual(channels.count, 1)
    }

    func testSignedOutScansStayOnThePhone() async throws {
        signedIn = false
        let streamer = makeStreamer()
        let scan = try manifest(rooms: 1)
        streamer.capture(link, reached: .started(scan))
        streamer.capture(link, reached: .roomSaved(index: 0, manifest: scan))
        await streamer.settle()
        XCTAssertTrue(creator.keys.isEmpty)
        XCTAssertTrue(uploader.calls.isEmpty)
        XCTAssertTrue(channels.isEmpty)
    }

    func testCreateRetriesInFlightConflictsWithTheSameKey() async throws {
        creator.fail(with: [.conflict(message: "in flight"), .offline])
        let streamer = makeStreamer()
        streamer.capture(link, reached: .started(try manifest()))
        await streamer.settle()
        XCTAssertEqual(creator.keys.count, 3)
        XCTAssertEqual(Set(creator.keys).count, 1)
        XCTAssertEqual(link.remoteIDs, ["remote-1"])
    }

    func testCreateGivesUpOnPermanentErrors() async throws {
        creator.fail(with: [.forbidden])
        let streamer = makeStreamer()
        streamer.capture(link, reached: .started(try manifest()))
        await streamer.settle()
        XCTAssertEqual(creator.keys.count, 1)
        XCTAssertTrue(link.remoteIDs.isEmpty)
    }

    func testEachFinishedRoomIsSentAndQueuedWithTheLatestMesh() async throws {
        let streamer = makeStreamer()
        let empty = try manifest()
        streamer.capture(link, reached: .started(empty))
        var withRoom = try manifest(rooms: 1)
        withRoom = ScanManifest(
            scanID: empty.scanID, name: empty.name, startedAt: empty.startedAt, phase: withRoom.phase, rooms: withRoom.rooms,
            meshFile: "mesh.spm", remoteScanID: "remote-1"
        )
        streamer.capture(link, reached: .roomSaved(index: 0, manifest: withRoom))
        streamer.capture(link, reached: .meshSaved(withRoom))
        await streamer.settle()

        XCTAssertEqual(uploader.calls, [
            .init(file: "room-0.json", scanID: "remote-1", kind: .room),
            .init(file: "mesh.spm", scanID: "remote-1", kind: .mesh),
        ])
        XCTAssertEqual(uploader.discards, [.mesh], "an older mesh still uploading is replaced")
        let sent = await channels[0].sent
        XCTAssertEqual(sent.map(\.roomID), ["room-0"])
        XCTAssertEqual(sent.first?.isFinal, true)
        XCTAssertNotNil(sent.first?.capturedRoom)
    }

    func testDetectorObjectsTravelAsObservationsWithTheRoom() async throws {
        let streamer = makeStreamer()
        let empty = try manifest()
        streamer.capture(link, reached: .started(empty))
        let saved = try manifest(rooms: 1)
        let fridge = DetectedObject(
            id: "detector-1", category: "refrigerator", label: "refrigerator",
            center: ScenePoint(x: 1, y: 0.85, z: 2), size: ScenePoint(x: 0.7, y: 1.7, z: 0.7), confidence: 0.8, hits: 4
        )
        try JSONEncoder().encode(DetectedObjectFile(objects: [fridge])).write(to: directory.appending(path: "room-0.detections.json"))
        let withRoom = ScanManifest(
            scanID: empty.scanID, name: empty.name, startedAt: empty.startedAt, phase: saved.phase, rooms: saved.rooms,
            meshFile: "mesh.spm", remoteScanID: "remote-1"
        )
        streamer.capture(link, reached: .roomSaved(index: 0, manifest: withRoom))
        await streamer.settle()

        let allSent = await channels[0].sent
        let sent = try XCTUnwrap(allSent.first)
        XCTAssertEqual(sent.roomID, "room-0", "the room id rule is unchanged")
        XCTAssertEqual(sent.observations, [try XCTUnwrap(fridge.observation)])
        XCTAssertEqual(uploader.calls.map(\.file), ["room-0.json"], "the server does not take the sidecar as an upload")
    }

    func testLiveRoomAndUploadedRoomShareOneServerID() async throws {
        let streamer = makeStreamer()
        let empty = try manifest()
        streamer.capture(link, reached: .started(empty))
        let file = "0.json"
        try Data(#"{"identifier":"7D1E-ROOM","walls":[]}"#.utf8).write(to: directory.appending(path: file))
        let withRoom = ScanManifest(
            scanID: empty.scanID, name: empty.name, startedAt: empty.startedAt, phase: .scanning(room: 1),
            rooms: [RoomRecord(index: 0, name: "Dining room", capturedRoomFile: file, completedAt: fixedNow)],
            meshFile: "mesh.spm", remoteScanID: "remote-1"
        )
        streamer.capture(link, reached: .roomSaved(index: 0, manifest: withRoom))
        await streamer.settle()

        let sent = await channels[0].sent
        XCTAssertEqual(sent.map(\.roomID), ["7D1E-ROOM"])
        XCTAssertEqual(uploader.calls.first?.file, file)
        XCTAssertEqual(RoomIdentity.names(of: withRoom, in: directory), ["7D1E-ROOM": "Dining room"])
    }

    func testResumeReusesThePersistedRemoteIDAndResendsSavedRooms() async throws {
        let streamer = makeStreamer()
        streamer.capture(link, reached: .resumed(try manifest(rooms: 2, remoteID: "remote-7")))
        await streamer.settle()
        XCTAssertTrue(creator.keys.isEmpty, "never create a second scan")
        XCTAssertEqual(streamer.remoteScanID, "remote-7")
        let sent = await channels[0].sent
        XCTAssertEqual(sent.map(\.roomID), ["room-0", "room-1"])
    }

    func testResumeFinishesAnInterruptedCreateWithTheSavedKey() async throws {
        let streamer = makeStreamer()
        streamer.capture(link, reached: .resumed(try manifest(rooms: 1, createKey: "saved-key")))
        await streamer.settle()
        XCTAssertEqual(creator.keys, ["saved-key"])
        XCTAssertEqual(link.remoteIDs, ["remote-1"])
        let sent = await channels[0].sent
        XCTAssertEqual(sent.map(\.roomID), ["room-0"])
    }

    func testServerFindingsReachTheCaptureScreen() async throws {
        let streamer = makeStreamer()
        streamer.capture(link, reached: .started(try manifest()))
        await streamer.settle()
        let finding = ServerFindingFixture.make(ruleID: "ADA-404", subjectID: "door-1")
        channels[0].deliver(.findings(RoomFindings(
            roomID: "room-0", seq: nil, isFinal: true, findings: [finding], summary: ServerFindingFixture.summary, elapsedMs: 4
        )))
        for _ in 0..<100 where link.merged.isEmpty {
            try await Task.sleep(for: .milliseconds(5))
        }
        XCTAssertEqual(link.merged.first?.map(\.ruleID), ["ADA-404"])
    }

    func testDeliveryWaitsForAnswersAndFailsWhenTheServerNeverAnswers() async throws {
        let streamer = makeStreamer()
        let scan = try manifest(rooms: 1, remoteID: "remote-1")
        streamer.capture(link, reached: .resumed(scan))
        await streamer.settle()
        try await streamer.deliverRooms(of: scan)

        await channels[0].setAnswersRooms(false)
        do {
            try await streamer.deliverRooms(of: scan)
            XCTFail("expected the rooms to count as undelivered")
        } catch {
            XCTAssertEqual(error as? ScanStreamingError, .roomsNotDelivered)
        }
    }

    func testDeliveryOpensAChannelAfterARelaunch() async throws {
        let streamer = makeStreamer()
        let scan = try manifest(rooms: 2, remoteID: "remote-3")
        try await streamer.deliverRooms(of: scan)
        let sent = await channels[0].sent
        XCTAssertEqual(sent.map(\.roomID), ["room-0", "room-1"])
    }

    func testDiscardClosesTheChannel() async throws {
        let streamer = makeStreamer()
        let scan = try manifest()
        streamer.capture(link, reached: .started(scan))
        streamer.capture(link, reached: .discarded(scanID: scan.scanID))
        await streamer.settle()
        let closed = await channels[0].closed
        XCTAssertTrue(closed)
    }
}

final class FindingMergeTests: XCTestCase {
    private func finding(_ rule: String, _ subject: String, _ status: FindingStatus) -> Finding {
        Finding(ruleID: rule, jurisdiction: .ada2010, section: "404", subjectID: subject, status: status, measured: nil, required: "", message: rule)
    }

    func testServerWinsForTheSameRuleAndSubject() {
        let merged = FindingMerge.preferringServer(
            onDevice: [finding("A", "door", .needsInfo), finding("B", "door", .pass)],
            server: [finding("A", "door", .fail)]
        )
        XCTAssertEqual(merged.map(\.status), [.pass, .fail])
    }

    func testUpsertReplacesInPlaceAndAppendsNew() {
        let merged = FindingMerge.upsert(
            [finding("A", "door", .fail), finding("C", "sink", .pass)],
            into: [finding("A", "door", .pass), finding("B", "door", .pass)]
        )
        XCTAssertEqual(merged.map(\.ruleID), ["A", "B", "C"])
        XCTAssertEqual(merged.first?.status, .fail)
    }
}

nonisolated enum ServerFindingFixture {
    static let summary = FindingsSummary(
        total: StatusCounts(pass: 0, fail: 1, needsInfo: 0, notApplicable: 0), byJurisdiction: [:], governing: nil, governingCounts: nil
    )

    static func make(ruleID: String, subjectID: String, jurisdiction: String = "ADA2010", status: FindingStatus = .fail) -> ServerFinding {
        ServerFinding(
            ruleID: ruleID, jurisdiction: jurisdiction, section: "404.2.3", title: "Door clear width", subjectID: subjectID,
            roomID: "room-0", status: status, severity: "violation", measured: nil, required: ">= 32 in", message: "Too narrow",
            evidence: "measured", location: nil, counterpart: nil
        )
    }
}
