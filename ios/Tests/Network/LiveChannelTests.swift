import XCTest
@testable import StandardPhysics

final class LiveMessageDecodingTests: XCTestCase {
    private func decode(_ json: String) throws -> LiveMessage {
        try WireCoding.decoder().decode(LiveMessage.self, from: Data(json.utf8))
    }

    func testDecodesEveryServerMessageKind() throws {
        let finding = try decode(findingJSON(eventID: 3))
        XCTAssertEqual(finding.eventID, 3)
        guard case .finding(let value) = finding.kind else { return XCTFail("not a finding") }
        XCTAssertEqual(value.ruleID, "ADA-404.2.4")
        XCTAssertEqual(value.status, .fail)

        XCTAssertEqual(
            try decode(#"{"type":"progress","event_id":4,"stage":"merge","fraction":0.5,"message":"Merging rooms"}"#).kind,
            .progress(ScanProgress(stage: "merge", fraction: 0.5, message: "Merging rooms"))
        )
        let id = UUID()
        XCTAssertEqual(try decode(#"{"type":"room_ack","event_id":5,"client_event_id":"\#(id)"}"#).kind, .roomAcknowledged(clientEventID: id))
        XCTAssertEqual(try decode(#"{"type":"scan_complete","event_id":6}"#).kind, .scanCompleted)
        XCTAssertEqual(try decode(#"{"type":"error","message":"Quota"}"#).kind, .serverError(message: "Quota"))
        XCTAssertEqual(try decode(#"{"type":"pong"}"#), LiveMessage(eventID: nil, kind: .heartbeat))
        XCTAssertEqual(try decode(#"{"type":"future_thing","event_id":9}"#).kind, .unknown(type: "future_thing"))
    }

    func testRoomFinishedEncodesSnakeCaseWithTypeTag() throws {
        let event = RoomFinishedEvent(clientEventID: UUID(uuidString: "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE")!, roomIndex: 2, name: "Kitchen", fileKey: "k/2")
        let object = try JSONSerialization.jsonObject(with: WireCoding.encoder().encode(event)) as? [String: Any]
        XCTAssertEqual(object?["type"] as? String, "room_finished")
        XCTAssertEqual(object?["room_index"] as? Int, 2)
        XCTAssertEqual(object?["file_key"] as? String, "k/2")
        XCTAssertEqual(object?["client_event_id"] as? String, "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE")
    }
}

func findingJSON(eventID: Int) -> String {
    """
    {"type":"finding","event_id":\(eventID),"finding":{"rule_id":"ADA-404.2.4","jurisdiction":"ADA2010","section":"404.2.4",
    "subject_id":"door-1","status":"fail","measured":{"value":0.6,"unit":"m"},"required":">= 0.815 m","message":"Too narrow"}}
    """
}

final class LiveChannelTests: XCTestCase {
    private func makeChannel(
        _ connector: FakeConnector, heartbeat: Duration = .seconds(30), pongTimeout: Duration = .milliseconds(100)
    ) -> LiveChannel {
        LiveChannel(
            requestProvider: { lastEventID in
                URLRequest(url: URL(string: "wss://live.test/scan?last_event_id=\(lastEventID.map(String.init) ?? "none")")!)
            },
            connector: connector,
            backoff: Backoff(base: .milliseconds(5), maximum: .milliseconds(20), jitter: { 0 }),
            heartbeatInterval: heartbeat,
            pongTimeout: pongTimeout
        )
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

    func testDeliversMessagesInOrderAndReportsConnectionStates() async {
        let socket = FakeSocket()
        let channel = makeChannel(FakeConnector(queued: [socket]))
        let messages = collectMessages(from: channel)
        let states = collectStates(from: channel)
        await channel.open()
        await eventually { states.read { $0.contains(.connected) } }

        socket.push(findingJSON(eventID: 1))
        socket.push(#"{"type":"progress","event_id":2,"stage":"rules","fraction":0.2}"#)
        await eventually { messages.read { $0.count } == 2 }
        XCTAssertEqual(messages.read { $0.map(\.eventID) }, [1, 2])
        XCTAssertEqual(states.read { Array($0.prefix(2)) }, [.connecting, .connected])
        await channel.close()
    }

    func testReconnectsAfterDropResumesFromLastEventAndDropsReplays() async {
        let first = FakeSocket()
        let second = FakeSocket()
        let connector = FakeConnector(queued: [first, second])
        let channel = makeChannel(connector)
        let messages = collectMessages(from: channel)
        await channel.open()
        await eventually { connector.connections.count == 1 }
        first.push(findingJSON(eventID: 4))
        first.push(findingJSON(eventID: 5))
        await eventually { messages.read { $0.count } == 2 }

        first.fail()
        await eventually { connector.connections.count == 2 }
        XCTAssertEqual(connector.requests[0].url?.query, "last_event_id=none")
        XCTAssertEqual(connector.requests[1].url?.query, "last_event_id=5")

        second.push(findingJSON(eventID: 5))
        second.push(findingJSON(eventID: 6))
        await eventually { messages.read { $0.count } == 3 }
        XCTAssertEqual(messages.read { $0.map(\.eventID) }, [4, 5, 6])
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

    func testRoomFinishedIsResentAfterReconnectUntilAcknowledged() async throws {
        let first = FakeSocket()
        let second = FakeSocket()
        let third = FakeSocket()
        let connector = FakeConnector(queued: [first, second, third])
        let channel = makeChannel(connector)
        await channel.open()
        await eventually { connector.connections.count == 1 }
        await eventually { first.pings >= 1 }

        let event = RoomFinishedEvent(roomIndex: 1, name: "Entry", fileKey: "scan/room-1.json")
        await channel.sendRoomFinished(event)
        await eventually { first.sent.count == 1 }
        XCTAssertTrue(first.sent[0].contains("\"room_finished\""))

        first.fail()
        await eventually { second.sent.count == 1 }
        XCTAssertEqual(second.sent, first.sent, "unacknowledged event is replayed verbatim")

        second.push(#"{"type":"room_ack","event_id":1,"client_event_id":"\#(event.clientEventID)"}"#)
        try await Task.sleep(for: .milliseconds(50))
        second.fail()
        await eventually { connector.connections.count == 3 }
        try await Task.sleep(for: .milliseconds(50))
        XCTAssertTrue(third.sent.isEmpty, "acknowledged event is not resent")
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
        socket.push(findingJSON(eventID: 1))
        await eventually { messages.read { $0.count } == 2 }
        XCTAssertEqual(messages.read { $0[0].kind }, .unknown(type: "undecodable"))
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
