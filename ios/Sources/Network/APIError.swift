import Foundation

nonisolated enum APIError: Error, Equatable, Sendable, LocalizedError {
    case notConfigured
    case offline
    case timedOut
    case cancelled
    case unauthorized
    case forbidden
    case notFound
    case conflict(message: String?)
    case rateLimited(retryAfter: TimeInterval?)
    case server(status: Int, message: String?)
    case rejected(status: Int, message: String?)
    case malformedResponse
    case responseTooLarge
    case transport(code: Int)

    static let maximumRetryAfter: TimeInterval = 60

    var errorDescription: String? { userMessage }

    var userMessage: String {
        switch self {
        case .notConfigured: "The app is missing its server address. Reinstall the app or contact support."
        case .offline: "You appear to be offline. Your scan is saved and will upload when you reconnect."
        case .timedOut: "The server took too long to respond. Check your connection and try again."
        case .cancelled: "The request was cancelled."
        case .unauthorized: "Your session has expired. Sign in again to continue."
        case .forbidden: "Your account does not have access to this scan."
        case .notFound: "The server could not find that scan or upload."
        case .conflict(let message): message ?? "That change conflicts with what is already on the server."
        case .rateLimited: "The server is busy. Wait a moment and try again."
        case .server: "The server ran into a problem. Your scan is safe on this phone, try again shortly."
        case .rejected(_, let message): message ?? "The server did not accept this request."
        case .malformedResponse: "The server sent a response the app could not read. Update the app and try again."
        case .responseTooLarge: "The server sent back far more data than expected, so the app stopped reading it. Try again later."
        case .transport: "The connection failed. Check your network and try again."
        }
    }

    var isTransient: Bool {
        switch self {
        case .offline, .timedOut, .rateLimited, .server, .transport: true
        default: false
        }
    }

    var suggestedRetryDelay: TimeInterval? {
        guard case .rateLimited(let retryAfter) = self else { return nil }
        return retryAfter
    }
}

extension APIError {
    init(transportError error: Error) {
        if error is CancellationError {
            self = .cancelled
            return
        }
        guard let urlError = error as? URLError else {
            self = .transport(code: (error as NSError).code)
            return
        }
        self = Self.fromURLError(urlError)
    }

    /// A server asking for a longer pause than a minute is not waited on longer than that.
    static func retryAfter(_ header: String?) -> TimeInterval? {
        guard let seconds = header.flatMap(TimeInterval.init), seconds >= 0 else { return nil }
        return min(seconds, maximumRetryAfter)
    }

    private static func fromURLError(_ error: URLError) -> APIError {
        switch error.code {
        case .cancelled: .cancelled
        case .timedOut: .timedOut
        case .notConnectedToInternet, .networkConnectionLost, .dataNotAllowed, .internationalRoamingOff: .offline
        default: .transport(code: error.errorCode)
        }
    }

    init(response: HTTPResponse) {
        let message = (try? WireCoding.decoder().decode(APIErrorBody.self, from: response.body))?.message
            .map(ServerText.sanitized)
        switch response.status {
        case 401: self = .unauthorized
        case 403: self = .forbidden
        case 404, 410: self = .notFound
        case 408: self = .timedOut
        case 409: self = .conflict(message: message)
        case 429: self = .rateLimited(retryAfter: Self.retryAfter(response.headers["retry-after"]))
        case 500...599: self = .server(status: response.status, message: message)
        default: self = .rejected(status: response.status, message: message)
        }
    }
}

/// Text from the server shown on screen: control characters removed and the length capped,
/// so a misbehaving server cannot fill the screen or smuggle in layout tricks.
nonisolated enum ServerText {
    static let maximumLength = 200

    static func sanitized(_ text: String) -> String {
        let visible = String(String.UnicodeScalarView(text.unicodeScalars.filter { !CharacterSet.controlCharacters.contains($0) }))
        let trimmed = visible.trimmingCharacters(in: .whitespaces)
        guard trimmed.count > maximumLength else { return trimmed }
        return String(trimmed.prefix(maximumLength - 1)) + "…"
    }
}
