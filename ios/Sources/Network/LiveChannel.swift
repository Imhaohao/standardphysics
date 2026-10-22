import Foundation
import os

nonisolated enum LiveConnectionState: Sendable, Equatable {
    case connecting
    case connected
    case reconnecting(attempt: Int)
    case closed
}

nonisolated enum LiveChannelError: Error, Equatable {
    case heartbeatTimedOut
}

/// Live link for one scan: sends room updates, receives findings and the final report.
/// Reconnects with exponential backoff. The server answers every connect with a `hello`
/// snapshot, so there is nothing to replay; updates the server has not answered yet are re-sent.
actor LiveChannel {
    typealias RequestProvider = @Sendable () async throws -> URLRequest

    nonisolated let messages: AsyncStream<LiveMessage>
    nonisolated let states: AsyncStream<LiveConnectionState>

    private let messageContinuation: AsyncStream<LiveMessage>.Continuation
    private let stateContinuation: AsyncStream<LiveConnectionState>.Continuation
    private let requestProvider: RequestProvider
    private let connector: any WebSocketConnecting
    private let backoff: Backoff
    private let heartbeatInterval: Duration
    private let pongTimeout: Duration
    private let sleep: Sleeper
    private let maximumConsecutiveFailures: Int
    private let logger = Logger(subsystem: "com.standardphysics.capture", category: "live")

    private var runTask: Task<Void, Never>?
    private var activeConnection: (any WebSocketConnection)?
    private var isClosed = false
    private var becameConnected = false
    private var unanswered: [RoomUpdate] = []

    init(
        requestProvider: @escaping RequestProvider,
        connector: any WebSocketConnecting = URLSessionWebSocketConnector(),
        backoff: Backoff = Backoff(base: .seconds(1), maximum: .seconds(30)),
        heartbeatInterval: Duration = .seconds(20),
        pongTimeout: Duration = .seconds(10),
        maximumConsecutiveFailures: Int = 10,
        sleep: @escaping Sleeper = DefaultSleeper.sleep
    ) {
        self.maximumConsecutiveFailures = maximumConsecutiveFailures
        (messages, messageContinuation) = AsyncStream.makeStream(of: LiveMessage.self, bufferingPolicy: .unbounded)
        (states, stateContinuation) = AsyncStream.makeStream(of: LiveConnectionState.self, bufferingPolicy: .bufferingNewest(8))
        self.requestProvider = requestProvider
        self.connector = connector
        self.backoff = backoff
        self.heartbeatInterval = heartbeatInterval
        self.pongTimeout = pongTimeout
        self.sleep = sleep
    }

    static func forScan(_ scanID: String, api: APIClient) -> LiveChannel {
        LiveChannel(requestProvider: { try await api.liveSocketRequest(scanID: scanID) })
    }

    func open() {
        guard runTask == nil, !isClosed else { return }
        runTask = Task { await self.runLoop() }
    }

    func close() {
        isClosed = true
        runTask?.cancel()
        activeConnection?.close()
        activeConnection = nil
        stateContinuation.yield(.closed)
        stateContinuation.finish()
        messageContinuation.finish()
    }

    /// True until the server has answered every room sent so far with findings.
    var hasUnansweredRooms: Bool { !unanswered.isEmpty }

    /// Kept until the server answers with findings for the room, and re-sent after every
    /// reconnect. The server merges observations by id, so repeats are harmless.
    func sendRoom(_ update: RoomUpdate) async {
        unanswered.append(update)
        guard let connection = activeConnection else { return }
        try? await transmit(update, over: connection)
    }

    // MARK: Connection loop

    /// Gives up for good when the server refuses the session (401 or 403), since retrying
    /// cannot fix that, or after `maximumConsecutiveFailures` attempts in a row fail.
    private func runLoop() async {
        var attempt = 0
        while !isClosed {
            stateContinuation.yield(attempt == 0 ? .connecting : .reconnecting(attempt: attempt))
            becameConnected = false
            let outcome = await runOneConnection()
            guard !isClosed else { return }
            attempt = becameConnected ? 1 : attempt + 1
            if outcome == .refused || attempt >= maximumConsecutiveFailures {
                close()
                return
            }
            try? await sleep(backoff.delay(forAttempt: attempt - 1))
        }
    }

    private enum ConnectionOutcome { case dropped, refused }

    private func runOneConnection() async -> ConnectionOutcome {
        let request: URLRequest
        do {
            request = try await requestProvider()
        } catch {
            return .dropped
        }
        let connection = connector.connect(request)
        defer {
            connection.close()
            activeConnection = nil
        }
        do {
            try await pingWithTimeout(connection)
            activeConnection = connection
            becameConnected = true
            stateContinuation.yield(.connected)
            try await resendUnanswered(over: connection)
            try await serve(connection)
        } catch {
            return Self.refusedStatuses.contains(connection.rejectionStatus ?? 0) ? .refused : .dropped
        }
        return .dropped
    }

    private static let refusedStatuses: Set<Int> = [401, 403]

    private func serve(_ connection: any WebSocketConnection) async throws {
        try await withThrowingTaskGroup(of: Void.self) { group in
            group.addTask { try await self.receiveLoop(connection) }
            group.addTask { try await self.heartbeatLoop(connection) }
            try await finishGroup(&group, closing: connection)
        }
    }

    private func receiveLoop(_ connection: any WebSocketConnection) async throws {
        while true {
            handle(try await connection.receive())
        }
    }

    private func heartbeatLoop(_ connection: any WebSocketConnection) async throws {
        while true {
            try await sleep(heartbeatInterval)
            try await pingWithTimeout(connection)
        }
    }

    private func pingWithTimeout(_ connection: any WebSocketConnection) async throws {
        let sleep = self.sleep
        let timeout = pongTimeout
        try await withThrowingTaskGroup(of: Void.self) { group in
            group.addTask { try await connection.ping() }
            group.addTask {
                try await sleep(timeout)
                throw LiveChannelError.heartbeatTimedOut
            }
            try await finishGroup(&group, closing: connection)
        }
    }

    /// Waits for the first child to finish. Closing the socket on failure matters because a
    /// blocked receive or ping only returns once the connection is torn down.
    private func finishGroup(_ group: inout ThrowingTaskGroup<Void, Error>, closing connection: any WebSocketConnection) async throws {
        defer { group.cancelAll() }
        do {
            try await group.next()
        } catch {
            connection.close()
            throw error
        }
    }

    // MARK: Messages

    private func handle(_ text: String) {
        let message = decode(text)
        if case .findings(let room) = message {
            acknowledge(room)
        }
        messageContinuation.yield(message)
    }

    private func acknowledge(_ answer: RoomFindings) {
        unanswered.removeAll { update in
            guard update.roomID == answer.roomID else { return false }
            guard let answered = answer.seq else { return true }
            return (update.seq ?? 0) <= answered
        }
    }

    private func decode(_ text: String) -> LiveMessage {
        if let decoded = try? WireCoding.decoder().decode(LiveMessage.self, from: Data(text.utf8)) { return decoded }
        logger.error("Undecodable live message of \(text.utf8.count) bytes")
        return .unknown(type: "undecodable")
    }

    private func resendUnanswered(over connection: any WebSocketConnection) async throws {
        for update in unanswered {
            try await transmit(update, over: connection)
        }
    }

    private func transmit(_ update: RoomUpdate, over connection: any WebSocketConnection) async throws {
        let data = try WireCoding.encoder().encode(update)
        try await connection.send(String(decoding: data, as: UTF8.self))
    }
}
