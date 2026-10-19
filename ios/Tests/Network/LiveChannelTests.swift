import XCTest
@testable import StandardPhysics

private let summaryJSON = #"{"total":{"pass":0,"fail":1,"needs_info":0,"not_applicable":0},"by_jurisdiction":{}}"#

private func findingJSON(subject: String = "door-1") -> String {
    """
    {"rule_id":"ADA-404.2.4","jurisdiction":"ADA2010","section":"404.2.4","title":"Door clearance","subject_id":"\(subject)",
    "room_id":"room-1","status":"fail","severity":"high","measured":{"text":"0.6 m","value":0.6,"lo":null,"hi":null,"unit":"m"},
    "required":">= 0.815 m","message":"Too narrow","evidence":"measured","location":null,"counterpart":null}
    """
}

func findingsMessage(room: String = "room-1", seq: Int? = nil, final: Bool = false) -> String {
    let seqText = seq.map(String.init) ?? "null"
    return #"{"type":"findings","room_id":"\#(room)","seq":\#(seqText),"final":\#(final),"findings":[\#(findingJSON())],"summary":\#(summaryJSON),"elapsed_ms":12}"#
}

final class LiveMessageDecodingTests: XCTestCase {
    private func decode(_ json: String) throws -> LiveMessage {
        try WireCoding.decoder().decode(LiveMessage.self, from: Data(json.utf8))
    }

    func testDecodesEveryServerMessageKind() throws {
        let hello = try decode(#"{"type":"hello","scan_id":"s1","rooms":["room-1"],"findings":[\#(findingJSON())],"summary":\#(summaryJSON)}"#)
        guard case .hello(let snapshot) = hello else { return XCTFail("not hello") }
        XCTAssertEqual(snapshot.rooms, ["room-1"])
        XCTAssertEqual(snapshot.findings.first?.ruleID, "ADA-404.2.4")

        guard case .findings(let room) = try decode(findingsMessage(seq: 7, final: true)) else { return XCTFail("not findings") }
        XCTAssertEqual([room.roomID, "\(room.seq ?? -1)", "\(room.isFinal)", "\(room.elapsedMs)"], ["room-1", "7", "true", "12"])
        XCTAssertEqual(room.findings.first?.status, .fail)

        XCTAssertEqual(try decode(#"{"type":"error","message":"Quota"}"#), .serverError(message: "Quota"))
        XCTAssertEqual(try decode(#"{"type":"pong"}"#), .pong)
        XCTAssertEqual(try decode(#"{"type":"room","room":{"id":"room-1","walls":[]}}"#), .room(.object(["id": .string("room-1"), "walls": .array([])])))
        XCTAssertEqual(try decode(#"{"type":"scene","scene":{"version":2}}"#), .scene(.object(["version": .number(2)])))
        XCTAssertEqual(try decode(#"{"type":"future_thing"}"#), .unknown(type: "future_thing"))
    }

    func testRoomUpdateEncodesServerClientMessage() throws {
        let update = RoomUpdate(
            roomID: LiveRoomID.make(index: 2), isFinal: true, seq: 4,
            capturedRoom: .object(["doors": .array([])]), observations: [.object(["id": .string("o1")])]
        )
        let object = try JSONSerialization.jsonObject(with: WireCoding.encoder().encode(update)) as? [String: Any]
        XCTAssertEqual(object?["type"] as? String, "room")
        XCTAssertEqual(object?["room_id"] as? String, "room-2")
        XCTAssertEqual(object?["final"] as? Bool, true)
        XCTAssertEqual(object?["seq"] as? Int, 4)
        XCTAssertNotNil(object?["captured_room"] as? [String: Any])
        XCTAssertEqual((object?["observations"] as? [[String: Any]])?.first?["id"] as? String, "o1")
    }

    func testRoomIDsRoundTripToIndexes() {
        XCTAssertEqual(LiveRoomID.index(of: LiveRoomID.make(index: 5)), 5)
        XCTAssertNil(LiveRoomID.index(of: "kitchen"))
    }
}

final class LiveChannelTests: XCTestCase {
    private func makeChannel(
        _ connector: FakeConnector, heartbeat: Duration = .seconds(30), pongTimeout: Duration = .milliseconds(100),
        maximumFailures: Int = 10
    ) -> LiveChannel {
        LiveChannel(
            requestProvider: { URLRequest(url: URL(string: "wss://live.test/v1/scans/s1/live")!) },
            connector: connector,
            backoff: Backoff(base: .milliseconds(5), maximum: .milliseconds(20), jitter: { 0 }),
            heartbeatInterval: heartbeat,
            pongTimeout: pongTimeout,
            maximumConsecutiveFailures: maximumFailures
        )
    }

    func testRefusedSessionStopsReconnecting() async {
        let refused = FakeSocket(pingBehavior: .fail)
        refused.reject(status: 401)
        let connector = FakeConnector(queued: [refused])
        let channel = makeChannel(connector)
        let states = collectStates(from: channel)
        await channel.open()
        await eventually { states.read { $0.contains(.closed) } }
        XCTAssertEqual(connector.connections.count, 1)
    }

    func testGivesUpAfterTooManyFailuresInARow() async {
        let sockets = (0..<6).map { _ in FakeSocket(pingBehavior: .fail) }
        let connector = FakeConnector(queued: sockets)
        let channel = makeChannel(connector, maximumFailures: 3)
        let states = collectStates(from: channel)
        await channel.open()
        await eventually { states.read { $0.contains(.closed) } }
        XCTAssertEqual(connector.connections.count, 3)
    }

    private func collectMessages(from channel: LiveChannel) -> Locked<[LiveMessage]> {
        let collected = Locked<[LiveMessage]>([])
        let stream = channel.messages
        Task { for await message in stream { collected.write { $0.append(message) } } }
        return collected
    }

    private func collectStates(from channel: LiveChannel) -> Locked<[LiveConnectionState]> {
        let collected = Locked<[LiveConnectionState]>([])
        let stream = channel.states
        Task { for await state in stream { collected.write { $0.append(state) } } }
        return collected
    }

    private func roomUpdate(_ room: String = "room-1", seq: Int?, final: Bool = false) -> RoomUpdate {
        RoomUpdate(roomID: room, isFinal: final, seq: seq, capturedRoom: .object(["id": .string(room)]), observations: [])
    }

    func testDeliversMessagesInOrderAndReportsConnectionStates() async {
        let socket = FakeSocket()
        let channel = makeChannel(FakeConnector(queued: [socket]))
        let messages = collectMessages(from: channel)
        let states = collectStates(from: channel)
        await channel.open()
        await eventually { states.read { $0.contains(.connected) } }

        socket.push(#"{"type":"hello","scan_id":"s1","rooms":[],"findings":[],"summary":\#(summaryJSON)}"#)
        socket.push(findingsMessage(seq: 1))
        await eventually { messages.read { $0.count } == 2 }
        guard case .hello = messages.read({ $0[0] }), case .findings = messages.read({ $0[1] }) else { return XCTFail("order") }
        XCTAssertEqual(states.read { Array($0.prefix(2)) }, [.connecting, .connected])
        await channel.close()
    }

    func testReconnectsAfterDropAndDeliversTheNewHelloSnapshot() async {
        let first = FakeSocket()
        let second = FakeSocket()
        let connector = FakeConnector(queued: [first, second])
        let channel = makeChannel(connector)
        let messages = collectMessages(from: channel)
        await channel.open()
        await eventually { connector.connections.count == 1 }
        first.push(findingsMessage(seq: 1))
        await eventually { messages.read { $0.count } == 1 }

        first.fail()
        await eventually { connector.connections.count == 2 }
        second.push(#"{"type":"hello","scan_id":"s1","rooms":["room-1"],"findings":[],"summary":\#(summaryJSON)}"#)
        await eventually { messages.read { $0.count } == 2 }
        guard case .hello(let snapshot) = messages.read({ $0[1] }) else { return XCTFail("expected hello") }
        XCTAssertEqual(snapshot.rooms, ["room-1"])
        await channel.close()
    }

    func testKeepsReconnectingWithBackoffWhileServerIsDown() async {
        let connector = FakeConnector(queued: [FakeSocket(pingBehavior: .fail), FakeSocket(pingBehavior: .fail), FakeSocket(pingBehavior: .fail)])
        let channel = makeChannel(connector)
        let states = collectStates(from: channel)
        await channel.open()
        await eventually { connector.connections.count >= 4 }
        XCTAssertTrue(states.read { $0.contains(.reconnecting(attempt: 3)) })
        await eventually { states.read { $0.contains(.connected) } }
        await channel.close()
    }

    func testRoomUpdatesAreResentAfterReconnectUntilServerAnswersWithFindings() async throws {
        let first = FakeSocket()
        let second = FakeSocket()
        let third = FakeSocket()
        let connector = FakeConnector(queued: [first, second, third])
        let channel = makeChannel(connector)
        await channel.open()
        await eventually { connector.connections.count == 1 }
        await eventually { first.pings >= 1 }

        await channel.sendRoom(roomUpdate(seq: 1))
        await channel.sendRoom(roomUpdate(seq: 2, final: true))
        await eventually { first.sent.count == 2 }
        XCTAssertTrue(first.sent[0].contains("\"type\":\"room\""))

        first.fail()
        await eventually { second.sent.count == 2 }
        XCTAssertEqual(second.sent, first.sent, "unanswered updates are replayed in order")

        second.push(findingsMessage(seq: 2, final: true))
        try await Task.sleep(for: .milliseconds(50))
        second.fail()
        await eventually { connector.connections.count == 3 }
        try await Task.sleep(for: .milliseconds(50))
        XCTAssertTrue(third.sent.isEmpty, "answered updates are not resent")
        await channel.close()
    }

    func testFindingsForAnOlderSeqKeepNewerUpdatesPending() async throws {
        let first = FakeSocket()
        let second = FakeSocket()
        let connector = FakeConnector(queued: [first, second])
        let channel = makeChannel(connector)
        await channel.open()
        await eventually { first.pings >= 1 }
        await channel.sendRoom(roomUpdate(seq: 1))
        await channel.sendRoom(roomUpdate(seq: 2))
        await eventually { first.sent.count == 2 }
        first.push(findingsMessage(seq: 1))
        try await Task.sleep(for: .milliseconds(50))
        first.fail()
        await eventually { second.sent.count == 1 }
        XCTAssertTrue(second.sent[0].contains("\"seq\":2"))
        await channel.close()
    }

    func testHeartbeatPingsHealthyConnection() async {
        let socket = FakeSocket()
        let channel = makeChannel(FakeConnector(queued: [socket]), heartbeat: .milliseconds(10))
        await channel.open()
        await eventually { socket.pings >= 4 }
        await channel.close()
    }

    func testUnansweredHeartbeatTriggersReconnect() async {
        let first = FakeSocket()
        let connector = FakeConnector(queued: [first, FakeSocket()])
        let channel = makeChannel(connector, heartbeat: .milliseconds(10), pongTimeout: .milliseconds(40))
        await channel.open()
        await eventually { first.pings >= 1 }
        first.setPingBehavior(.hang)
        await eventually { connector.connections.count == 2 }
        XCTAssertTrue(first.isClosed)
        await channel.close()
    }

    func testUndecodableFrameDoesNotDropConnection() async {
        let socket = FakeSocket()
        let connector = FakeConnector(queued: [socket])
        let channel = makeChannel(connector)
        let messages = collectMessages(from: channel)
        await channel.open()
        await eventually { connector.connections.count == 1 }
        socket.push("{{{")
        socket.push(#"{"type":"pong"}"#)
        await eventually { messages.read { $0.count } == 2 }
        XCTAssertEqual(messages.read { $0[0] }, .unknown(type: "undecodable"))
        XCTAssertEqual(connector.connections.count, 1)
        await channel.close()
    }

    func testCloseTearsDownSocketAndFinishesStreams() async {
        let socket = FakeSocket()
        let connector = FakeConnector(queued: [socket])
        let channel = makeChannel(connector)
        let states = collectStates(from: channel)
        await channel.open()
        await eventually { states.read { $0.contains(.connected) } }
        await channel.close()
        await eventually { socket.isClosed }
        await eventually { states.read { $0.last } == .closed }
        try? await Task.sleep(for: .milliseconds(80))
        XCTAssertEqual(connector.connections.count, 1, "no reconnect after close")
    }
}
