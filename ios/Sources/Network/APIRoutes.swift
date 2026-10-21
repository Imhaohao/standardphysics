import Foundation

nonisolated enum HTTPMethod: String, Sendable {
    case get = "GET"
    case post = "POST"
    case put = "PUT"
    case patch = "PATCH"
    case delete = "DELETE"
}

nonisolated struct Endpoint<Response: Decodable & Sendable>: Sendable {
    let method: HTTPMethod
    let path: String
    var query: [URLQueryItem] = []
    var headers: [String: String] = [:]
    var body: (any Encodable & Sendable)?
    var requiresAuth = true
    var isIdempotent: Bool
    var timeout: TimeInterval?
}

/// The single place that knows server paths (server/openapi.json). Swapping contracts
/// changes only this file and APIModels.swift.
nonisolated enum APIRoutes {
    static let apiPrefix = "/v1"
    static let finishTimeout: TimeInterval = 120
    static let idempotencyHeader = "Idempotency-Key"

    static func register(_ body: Credentials) -> Endpoint<AuthSession> {
        Endpoint(method: .post, path: "\(apiPrefix)/auth/register", body: body, requiresAuth: false, isIdempotent: false)
    }

    static func login(_ body: Credentials) -> Endpoint<AuthSession> {
        Endpoint(method: .post, path: "\(apiPrefix)/auth/login", body: body, requiresAuth: false, isIdempotent: false)
    }

    static func signInWithApple(_ body: AppleSignInRequest) -> Endpoint<AuthSession> {
        Endpoint(method: .post, path: "\(apiPrefix)/auth/apple", body: body, requiresAuth: false, isIdempotent: false)
    }

    static func logout() -> Endpoint<EmptyResponse> {
        Endpoint(method: .post, path: "\(apiPrefix)/auth/logout", isIdempotent: true)
    }

    static func me() -> Endpoint<ServerUser> {
        Endpoint(method: .get, path: "\(apiPrefix)/me", isIdempotent: true)
    }

    /// Removes the user, their sessions, scans and stored files. Not retried: a repeat after a
    /// dropped response would only fail on the token the first one revoked.
    static func deleteAccount() -> Endpoint<EmptyResponse> {
        Endpoint(method: .delete, path: "\(apiPrefix)/me", isIdempotent: false)
    }

    /// Safe to retry because the key is persisted before the first attempt; a repeat with the
    /// same key replays the first scan instead of making a second one.
    static func createScan(_ body: CreateScanRequest, idempotencyKey: String) -> Endpoint<ScanResponse> {
        Endpoint(
            method: .post, path: "\(apiPrefix)/scans", headers: [idempotencyHeader: idempotencyKey],
            body: body, isIdempotent: true
        )
    }

    static func listScans() -> Endpoint<[ScanResponse]> {
        Endpoint(method: .get, path: "\(apiPrefix)/scans", isIdempotent: true)
    }

    static func renameScan(scanID: String, body: RenameScanRequest) -> Endpoint<ScanResponse> {
        Endpoint(method: .patch, path: "\(apiPrefix)/scans/\(scanID)", body: body, isIdempotent: true)
    }

    /// Removes the scan's rows and stored files on the server.
    static func deleteScan(scanID: String) -> Endpoint<EmptyResponse> {
        Endpoint(method: .delete, path: "\(apiPrefix)/scans/\(scanID)", isIdempotent: true)
    }

    static func assessment(scanID: String) -> Endpoint<Report> {
        Endpoint(method: .get, path: "\(apiPrefix)/scans/\(scanID)/assessment", isIdempotent: true)
    }

    static func answers(scanID: String) -> Endpoint<[ServerAnswer]> {
        Endpoint(method: .get, path: "\(apiPrefix)/scans/\(scanID)/answers", isIdempotent: true)
    }

    /// Answers the server already holds are replaced, so sending the same set twice is harmless.
    /// The response is the report checked again with the answers.
    static func saveAnswers(scanID: String, body: AnswersRequest) -> Endpoint<Report> {
        Endpoint(method: .put, path: "\(apiPrefix)/scans/\(scanID)/answers", body: body, isIdempotent: true)
    }

    /// The merged scene the server checked, used to name what each finding is about.
    static func scene(scanID: String) -> Endpoint<JSONValue> {
        Endpoint(method: .get, path: "\(apiPrefix)/scans/\(scanID)/scene", isIdempotent: true)
    }

    static func finishScan(scanID: String) -> Endpoint<Report> {
        Endpoint(method: .post, path: "\(apiPrefix)/scans/\(scanID)/finish", isIdempotent: false, timeout: finishTimeout)
    }

    static func createUpload(scanID: String, body: CreateUploadBody, idempotencyKey: String) -> Endpoint<UploadInfo> {
        Endpoint(
            method: .post, path: "\(apiPrefix)/scans/\(scanID)/uploads", headers: [idempotencyHeader: idempotencyKey],
            body: body, isIdempotent: true
        )
    }

    static func uploadStatus(scanID: String, uploadID: String) -> Endpoint<UploadStatusResponse> {
        Endpoint(method: .get, path: "\(apiPrefix)/scans/\(scanID)/uploads/\(uploadID)", isIdempotent: true)
    }

    static func presignParts(scanID: String, uploadID: String, body: PresignRequest) -> Endpoint<PresignResponse> {
        Endpoint(method: .post, path: "\(apiPrefix)/scans/\(scanID)/uploads/\(uploadID)/parts", body: body, isIdempotent: true)
    }

    static func completeUpload(scanID: String, uploadID: String, body: CompleteUploadRequest) -> Endpoint<Artifact> {
        Endpoint(method: .post, path: "\(apiPrefix)/scans/\(scanID)/uploads/\(uploadID)/complete", body: body, isIdempotent: true)
    }

    static func abortUpload(scanID: String, uploadID: String) -> Endpoint<EmptyResponse> {
        Endpoint(method: .post, path: "\(apiPrefix)/scans/\(scanID)/uploads/\(uploadID)/abort", isIdempotent: true)
    }

    static func livePath(scanID: String) -> String {
        "\(apiPrefix)/scans/\(scanID)/live"
    }
}
