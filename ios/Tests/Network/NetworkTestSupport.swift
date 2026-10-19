import Foundation
import XCTest
@testable import StandardPhysics

final class Locked<Value>: @unchecked Sendable {
    private let lock = NSLock()
    private var value: Value

    init(_ value: Value) { self.value = value }

    func read<T>(_ body: (Value) -> T) -> T { lock.withLock { body(value) } }
    func write<T>(_ body: (inout Value) -> T) -> T { lock.withLock { body(&value) } }
}

func eventually(
    timeout: TimeInterval = 5, file: StaticString = #filePath, line: UInt = #line,
    _ condition: @escaping () async -> Bool
) async {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
        if await condition() { return }
        try? await Task.sleep(for: .milliseconds(10))
    }
    XCTFail("Condition not met within \(timeout)s", file: file, line: line)
}

func makeTemporaryDirectory() throws -> URL {
    let url = FileManager.default.temporaryDirectory.appendingPathComponent("sp-net-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}

func makeRandomFile(in directory: URL, name: String = "room.json", size: Int) throws -> URL {
    var generator = SplitMix64(seed: UInt64(size))
    let bytes = (0..<size).map { _ in UInt8(truncatingIfNeeded: generator.next()) }
    let url = directory.appendingPathComponent(name)
    try Data(bytes).write(to: url)
    return url
}

struct SplitMix64 {
    var state: UInt64
    init(seed: UInt64) { state = seed }

    mutating func next() -> UInt64 {
        state &+= 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }
}

let fixedNow = Date(timeIntervalSince1970: 1_800_000_000)

// MARK: HTTP

final class InMemoryTokenStore: TokenStoring, @unchecked Sendable {
    private let stored = Locked<String?>(nil)

    init(token: String? = nil) { stored.write { $0 = token } }

    func token() -> String? { stored.read { $0 } }
    func save(_ token: String) throws { stored.write { $0 = token } }
    func clear() { stored.write { $0 = nil } }
}

final class ScriptedTransport: HTTPTransport, @unchecked Sendable {
    private let script: Locked<[Result<HTTPResponse, Error>]>
    private let seen = Locked<[URLRequest]>([])

    init(_ script: [Result<HTTPResponse, Error>]) { self.script = Locked(script) }

    var requests: [URLRequest] { seen.read { $0 } }

    func send(_ request: URLRequest) async throws -> HTTPResponse {
        seen.write { $0.append(request) }
        guard let next = script.write({ $0.isEmpty ? nil : $0.removeFirst() }) else { throw URLError(.badServerResponse) }
        return try next.get()
    }
}

func jsonResponse(_ status: Int = 200, _ json: String, headers: [String: String] = [:]) -> Result<HTTPResponse, Error> {
    .success(HTTPResponse(status: status, headers: headers, body: Data(json.utf8)))
}

final class RecordingSleeper: @unchecked Sendable {
    private let recorded = Locked<[Duration]>([])
    var durations: [Duration] { recorded.read { $0 } }
    var sleeper: Sleeper { { [recorded] duration in recorded.write { $0.append(duration) } } }
}

// MARK: Uploads

final class FakeUploadAPI: UploadAPI, @unchecked Sendable {
    struct RequestCall { let scanID: String; let body: RequestUploadBody; let clientFileID: UUID }
    struct CompleteCall { let uploadID: String; let parts: [CompletedPart] }

    private let state = Locked(State())
    private struct State {
        var requests: [RequestCall] = []
        var refreshes: [[Int]] = []
        var completions: [CompleteCall] = []
        var requestErrors: [APIError] = []
    }

    var urlTimeToLive: TimeInterval = 3600
    var now: Date = fixedNow

    var requestCalls: [RequestCall] { state.read { $0.requests } }
    var refreshCalls: [[Int]] { state.read { $0.refreshes } }
    var completeCalls: [CompleteCall] { state.read { $0.completions } }

    func failNextRequests(with errors: [APIError]) { state.write { $0.requestErrors = errors } }

    func requestUpload(scanID: String, file: RequestUploadBody, clientFileID: UUID) async throws -> MultipartUploadGrant {
        state.write { $0.requests.append(RequestCall(scanID: scanID, body: file, clientFileID: clientFileID)) }
        if let error = state.write({ $0.requestErrors.isEmpty ? nil : $0.requestErrors.removeFirst() }) { throw error }
        let count = PartSlicer.partCount(fileSize: file.sizeBytes, partSize: file.partSize)
        let parts = (1...count).map { presigned(upload: "up-\(clientFileID.uuidString.prefix(4))", number: $0, label: "granted") }
        return MultipartUploadGrant(uploadID: "up-\(clientFileID.uuidString.prefix(4))", partSize: file.partSize, parts: parts)
    }

    func refreshPartURLs(scanID: String, uploadID: String, partNumbers: [Int]) async throws -> [PresignedPart] {
        state.write { $0.refreshes.append(partNumbers) }
        return partNumbers.map { presigned(upload: uploadID, number: $0, label: "refreshed", ttl: 3600) }
    }

    func completeUpload(scanID: String, uploadID: String, parts: [CompletedPart]) async throws {
        state.write { $0.completions.append(CompleteCall(uploadID: uploadID, parts: parts)) }
    }

    private func presigned(upload: String, number: Int, label: String, ttl: TimeInterval? = nil) -> PresignedPart {
        PresignedPart(
            partNumber: number,
            url: URL(string: "https://r2.test/\(upload)/\(label)/part-\(number)")!,
            expiresAt: now.addingTimeInterval(ttl ?? urlTimeToLive)
        )
    }
}

final class FakeUploadSession: UploadTaskSession, @unchecked Sendable {
    struct Started { let id: Int; let label: String; let url: URL; let body: Data }

    let events: AsyncStream<UploadTaskEvent>
    private let continuation: AsyncStream<UploadTaskEvent>.Continuation
    private let state = Locked(State())
    private struct State {
        var started: [Started] = []
        var live: [LiveUploadTask] = []
        var cancelled: [Int] = []
        var nextID = 1
        var backgroundHandler: (@Sendable () -> Void)?
        var autoSucceed = false
    }

    init(alreadyRunning: [LiveUploadTask] = [], autoSucceed: Bool = false) {
        (events, continuation) = AsyncStream.makeStream(of: UploadTaskEvent.self, bufferingPolicy: .unbounded)
        state.write { $0.live = alreadyRunning; $0.nextID = 1000; $0.autoSucceed = autoSucceed }
    }

    var started: [Started] { state.read { $0.started } }
    var startedLabels: [String] { started.map(\.label) }
    var cancelledIDs: [Int] { state.read { $0.cancelled } }

    func startUpload(request: URLRequest, fileURL: URL, label: String) -> Int {
        let body = (try? Data(contentsOf: fileURL)) ?? Data()
        let (id, autoSucceed) = state.write { state -> (Int, Bool) in
            let id = state.nextID
            state.nextID += 1
            state.started.append(Started(id: id, label: label, url: request.url!, body: body))
            state.live.append(LiveUploadTask(id: id, label: label))
            return (id, state.autoSucceed)
        }
        if autoSucceed { succeed(label) }
        return id
    }

    func progress(_ label: String, bytes: Int64) {
        continuation.yield(.progress(label: label, bytesSent: bytes))
    }

    func liveTasks() async -> [LiveUploadTask] { state.read { $0.live } }

    func cancelTask(id: Int) async {
        state.write {
            $0.cancelled.append(id)
            $0.live.removeAll { $0.id == id }
        }
    }

    func setBackgroundEventsCompletion(_ handler: @escaping @Sendable () -> Void) {
        state.write { $0.backgroundHandler = handler }
    }

    func fireBackgroundEventsCompletion() { state.read { $0.backgroundHandler }?() }

    func finish(_ label: String, _ outcome: UploadTaskOutcome) {
        state.write { $0.live.removeAll { $0.label == label } }
        continuation.yield(.finished(label: label, outcome: outcome))
    }

    func succeed(_ label: String) {
        finish(label, .succeeded(etag: "\"etag-\(label.split(separator: "#").last ?? "")\""))
    }
}

func partLabel(_ fileID: UUID, _ number: Int) -> String { PartKey(fileID: fileID, number: number).label }

// MARK: WebSocket

final class FakeSocket: WebSocketConnection, @unchecked Sendable {
    enum PingBehavior { case succeed, fail, hang }

    private let record = Locked(Record())
    private struct Record {
        var sent: [String] = []
        var pings = 0
        var closed = false
        var pingBehavior = PingBehavior.succeed
        var inbox: [Result<String, Error>] = []
        var waiter: CheckedContinuation<String, Error>?
    }

    init(pingBehavior: PingBehavior = .succeed) {
        record.write { $0.pingBehavior = pingBehavior }
    }

    var sent: [String] { record.read { $0.sent } }
    var pings: Int { record.read { $0.pings } }
    var isClosed: Bool { record.read { $0.closed } }

    func setPingBehavior(_ behavior: PingBehavior) { record.write { $0.pingBehavior = behavior } }
    func push(_ text: String) { deliver(.success(text)) }
    func fail(_ error: Error = URLError(.networkConnectionLost)) { deliver(.failure(error)) }

    private func deliver(_ result: Result<String, Error>) {
        let waiter = record.write { state -> CheckedContinuation<String, Error>? in
            guard let waiter = state.waiter else {
                state.inbox.append(result)
                return nil
            }
            state.waiter = nil
            return waiter
        }
        waiter?.resume(with: result)
    }

    func send(_ text: String) async throws { record.write { $0.sent.append(text) } }

    func receive() async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            let ready = record.write { state -> Result<String, Error>? in
                if !state.inbox.isEmpty { return state.inbox.removeFirst() }
                state.waiter = continuation
                return nil
            }
            if let ready { continuation.resume(with: ready) }
        }
    }

    func ping() async throws {
        let behavior = record.write { state -> PingBehavior in
            state.pings += 1
            return state.pingBehavior
        }
        switch behavior {
        case .succeed: return
        case .fail: throw URLError(.networkConnectionLost)
        case .hang: try await Task.sleep(for: .seconds(60))
        }
    }

    func close() {
        record.write { $0.closed = true }
        deliver(.failure(URLError(.cancelled)))
    }
}

final class FakeConnector: WebSocketConnecting, @unchecked Sendable {
    private let state = Locked(State())
    private struct State {
        var queued: [FakeSocket] = []
        var connections: [FakeSocket] = []
        var requests: [URLRequest] = []
    }

    init(queued: [FakeSocket] = []) { state.write { $0.queued = queued } }

    var requests: [URLRequest] { state.read { $0.requests } }
    var connections: [FakeSocket] { state.read { $0.connections } }

    func connect(_ request: URLRequest) -> any WebSocketConnection {
        state.write { state in
            let socket = state.queued.isEmpty ? FakeSocket() : state.queued.removeFirst()
            state.connections.append(socket)
            state.requests.append(request)
            return socket
        }
    }
}
