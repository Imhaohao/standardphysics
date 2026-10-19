import Foundation

nonisolated struct LiveUploadTask: Sendable, Equatable {
    let id: Int
    let label: String
}

nonisolated enum UploadTaskOutcome: Sendable, Equatable {
    case succeeded(etag: String?)
    case failed(statusCode: Int?, message: String)
    case cancelled
}

nonisolated enum UploadTaskEvent: Sendable, Equatable {
    case progress(label: String, bytesSent: Int64)
    case finished(label: String, outcome: UploadTaskOutcome)
}

/// The slice of URLSession the uploader needs. A fake implements it in tests.
nonisolated protocol UploadTaskSession: Sendable {
    var events: AsyncStream<UploadTaskEvent> { get }
    func startUpload(request: URLRequest, fileURL: URL, label: String) -> Int
    func liveTasks() async -> [LiveUploadTask]
    func cancelTask(id: Int) async
    func setBackgroundEventsCompletion(_ handler: @escaping @Sendable () -> Void)
}

nonisolated final class URLSessionUploadDriver: NSObject, UploadTaskSession, URLSessionTaskDelegate, @unchecked Sendable {
    static let defaultIdentifier = "com.tarunyadgirkar.standardphysics.upload"

    let events: AsyncStream<UploadTaskEvent>
    private let continuation: AsyncStream<UploadTaskEvent>.Continuation
    private let completionLock = NSLock()
    private var backgroundCompletion: (@Sendable () -> Void)?
    private var session: URLSession!

    init(identifier: String = URLSessionUploadDriver.defaultIdentifier) {
        (events, continuation) = AsyncStream.makeStream(of: UploadTaskEvent.self, bufferingPolicy: .unbounded)
        super.init()
        session = URLSession(configuration: Self.configuration(identifier: identifier), delegate: self, delegateQueue: nil)
    }

    static func configuration(identifier: String) -> URLSessionConfiguration {
        let configuration = URLSessionConfiguration.background(withIdentifier: identifier)
        configuration.sessionSendsLaunchEvents = true
        configuration.isDiscretionary = false
        configuration.allowsCellularAccess = true
        configuration.waitsForConnectivity = true
        configuration.httpMaximumConnectionsPerHost = 4
        return configuration
    }

    func startUpload(request: URLRequest, fileURL: URL, label: String) -> Int {
        let task = session.uploadTask(with: request, fromFile: fileURL)
        task.taskDescription = label
        task.resume()
        return task.taskIdentifier
    }

    func liveTasks() async -> [LiveUploadTask] {
        await session.allTasks.compactMap { task in
            guard task.state == .running || task.state == .suspended, let label = task.taskDescription else { return nil }
            return LiveUploadTask(id: task.taskIdentifier, label: label)
        }
    }

    func cancelTask(id: Int) async {
        await session.allTasks.first { $0.taskIdentifier == id }?.cancel()
    }

    func setBackgroundEventsCompletion(_ handler: @escaping @Sendable () -> Void) {
        completionLock.withLock { backgroundCompletion = handler }
    }

    func urlSession(
        _ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64,
        totalBytesSent: Int64, totalBytesExpectedToSend: Int64
    ) {
        guard let label = task.taskDescription else { return }
        continuation.yield(.progress(label: label, bytesSent: totalBytesSent))
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard let label = task.taskDescription else { return }
        continuation.yield(.finished(label: label, outcome: Self.outcome(for: task, error: error)))
    }

    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        let handler = completionLock.withLock {
            let pending = backgroundCompletion
            backgroundCompletion = nil
            return pending
        }
        guard let handler else { return }
        DispatchQueue.main.async { handler() }
    }

    static func outcome(for task: URLSessionTask, error: Error?) -> UploadTaskOutcome {
        if let urlError = error as? URLError, urlError.code == .cancelled { return .cancelled }
        let http = task.response as? HTTPURLResponse
        if let error { return .failed(statusCode: http?.statusCode, message: error.localizedDescription) }
        guard let http, (200..<300).contains(http.statusCode) else {
            return .failed(statusCode: (task.response as? HTTPURLResponse)?.statusCode, message: "Upload was rejected")
        }
        return .succeeded(etag: http.value(forHTTPHeaderField: "ETag"))
    }
}
