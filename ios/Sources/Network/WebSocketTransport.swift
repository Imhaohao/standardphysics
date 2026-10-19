import Foundation

nonisolated protocol WebSocketConnection: Sendable {
    func send(_ text: String) async throws
    func receive() async throws -> String
    func ping() async throws
    func close()
}

nonisolated protocol WebSocketConnecting: Sendable {
    func connect(_ request: URLRequest) -> any WebSocketConnection
}

nonisolated struct URLSessionWebSocketConnector: WebSocketConnecting {
    let session: URLSession

    init(session: URLSession = URLSession(configuration: .default)) {
        self.session = session
    }

    func connect(_ request: URLRequest) -> any WebSocketConnection {
        let task = session.webSocketTask(with: request)
        task.resume()
        return URLSessionWebSocketConnection(task: task)
    }
}

nonisolated struct URLSessionWebSocketConnection: WebSocketConnection {
    let task: URLSessionWebSocketTask

    func send(_ text: String) async throws {
        try await task.send(.string(text))
    }

    func receive() async throws -> String {
        switch try await task.receive() {
        case .string(let text): return text
        case .data(let data): return String(decoding: data, as: UTF8.self)
        @unknown default: throw APIError.malformedResponse
        }
    }

    func ping() async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            task.sendPing { error in
                if let error { continuation.resume(throwing: error) } else { continuation.resume() }
            }
        }
    }

    func close() {
        task.cancel(with: .goingAway, reason: nil)
    }
}
