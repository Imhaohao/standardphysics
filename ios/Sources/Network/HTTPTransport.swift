import Foundation

nonisolated struct HTTPResponse: Sendable, Equatable {
    let status: Int
    /// Header names are lowercased.
    let headers: [String: String]
    let body: Data

    var isSuccess: Bool { (200..<300).contains(status) }
}

nonisolated protocol HTTPTransport: Sendable {
    func send(_ request: URLRequest) async throws -> HTTPResponse
}

nonisolated struct URLSessionTransport: HTTPTransport {
    /// The largest reply the app accepts. A full report is well under a megabyte, so anything
    /// past this is a broken or hostile server and is cut off before it fills memory.
    static let maximumResponseBytes = 5 * 1024 * 1024

    let session: URLSession

    init(session: URLSession = URLSessionTransport.makeDefaultSession()) {
        self.session = session
    }

    static func makeDefaultSession() -> URLSession {
        let configuration = URLSessionConfiguration.default
        configuration.waitsForConnectivity = false
        configuration.timeoutIntervalForRequest = 30
        return URLSession(configuration: configuration)
    }

    func send(_ request: URLRequest) async throws -> HTTPResponse {
        let (bytes, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.malformedResponse }
        guard http.expectedContentLength <= Int64(Self.maximumResponseBytes) else {
            bytes.task.cancel()
            throw APIError.responseTooLarge
        }
        let data = try await Self.collect(bytes, limit: Self.maximumResponseBytes)
        var headers: [String: String] = [:]
        for (key, value) in http.allHeaderFields {
            guard let key = key as? String, let value = value as? String else { continue }
            headers[key.lowercased()] = value
        }
        return HTTPResponse(status: http.statusCode, headers: headers, body: data)
    }

    static func collect<Bytes: AsyncSequence>(_ bytes: Bytes, limit: Int) async throws -> Data where Bytes.Element == UInt8 {
        var data = Data()
        for try await byte in bytes {
            guard data.count < limit else { throw APIError.responseTooLarge }
            data.append(byte)
        }
        return data
    }
}
