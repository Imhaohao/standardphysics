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
    struct CreateCall { let scanID: String; let body: CreateUploadBody; var idempotencyKey = "" }
    struct CompleteCall { let uploadID: String; let sha256: String }

    private let state = Locked(State())
    private struct State {
        var creates: [CreateCall] = []
        var presigns: [[Int]] = []
        var statusCalls = 0
        var completions: [CompleteCall] = []
        var createErrors: [APIError] = []
        var uploadState = "open"
        var storedParts: [Int] = []
    }

    var urlTimeToLive = 3600

    var createCalls: [CreateCall] { state.read { $0.creates } }
    var presignCalls: [[Int]] { state.read { $0.presigns } }
    var statusCallCount: Int { state.read { $0.statusCalls } }
    var completeCalls: [CompleteCall] { state.read { $0.completions } }

    func failNextCreates(with errors: [APIError]) { state.write { $0.createErrors = errors } }
    func setServerUpload(state uploadState: String, storedParts: [Int]) {
        state.write {
            $0.uploadState = uploadState
            $0.storedParts = storedParts
        }
    }

    func createUpload(scanID: String, body: CreateUploadBody, idempotencyKey: String) async throws -> UploadInfo {
        state.write { $0.creates.append(CreateCall(scanID: scanID, body: body, idempotencyKey: idempotencyKey)) }
        if let error = state.write({ $0.createErrors.isEmpty ? nil : $0.createErrors.removeFirst() }) { throw error }
        let partSize = body.partSize ?? 8 * 1024 * 1024
        return info(scanID: scanID, size: body.sizeBytes, partSize: partSize, kind: body.kind, name: body.filename, state: "open")
    }

    func uploadStatus(scanID: String, uploadID: String) async throws -> UploadStatusResponse {
        let (uploadState, stored, call) = state.write { state -> (String, [Int], CreateCall?) in
            state.statusCalls += 1
            return (state.uploadState, state.storedParts, state.creates.last)
        }
        let size = call?.body.sizeBytes ?? 0
        let partSize = call?.body.partSize ?? 1
        let upload = info(scanID: scanID, size: size, partSize: partSize, kind: "room", name: "x", state: uploadState)
        let parts = stored.map {
            UploadedPart(partNumber: $0, etag: "\"server-\($0)\"", sizeBytes: PartSlicer.partLength(partNumber: $0, fileSize: size, partSize: partSize))
        }
        return UploadStatusResponse(upload: upload, uploadedParts: parts)
    }

    func presignParts(scanID: String, uploadID: String, partNumbers: [Int]) async throws -> PresignResponse {
        state.write { $0.presigns.append(partNumbers) }
        let parts = partNumbers.map {
            PresignedPart(partNumber: $0, url: URL(string: "https://r2.test/\(uploadID)/presigned/part-\($0)")!, headers: ["x-amz-test": "1"])
        }
        return PresignResponse(parts: parts, expiresInSecs: urlTimeToLive)
    }

    func completeUpload(scanID: String, uploadID: String, sha256: String) async throws -> Artifact {
        state.write { $0.completions.append(CompleteCall(uploadID: uploadID, sha256: sha256)) }
        return Artifact(
            id: "a1", scanID: scanID, uploadID: uploadID, kind: "room", filename: "x", contentType: "x",
            sizeBytes: 1, sha256: sha256, createdAt: fixedNow
        )
    }

    private func info(scanID: String, size: Int64, partSize: Int, kind: String, name: String, state: String) -> UploadInfo {
        UploadInfo(
            id: "up-1", scanID: scanID, kind: kind, filename: name, contentType: "application/json", sizeBytes: size,
            partSize: partSize, partCount: PartSlicer.partCount(fileSize: size, partSize: partSize), state: state, createdAt: fixedNow
        )
    }
}

final class FakeUploadSession: UploadTaskSession, @unchecked Sendable {
    struct Started { let id: Int; let label: String; let url: URL; let body: Data; let headers: [String: String] }

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
            state.started.append(Started(id: id, label: label, url: request.url!, body: body, headers: request.allHTTPHeaderFields ?? [:]))
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
        var rejectionStatus: Int?
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
    var rejectionStatus: Int? { record.read { $0.rejectionStatus } }
    func reject(status: Int) { record.write { $0.rejectionStatus = status } }
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
