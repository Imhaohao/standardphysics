import Foundation

nonisolated enum HTTPMethod: String, Sendable {
    case get = "GET"
    case post = "POST"
}

nonisolated struct Endpoint<Response: Decodable & Sendable>: Sendable {
    let method: HTTPMethod
    let path: String
    var query: [URLQueryItem] = []
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

    /// Not idempotent: the server has no client id, so a retried create makes a second scan.
    static func createScan(_ body: CreateScanRequest) -> Endpoint<ScanResponse> {
        Endpoint(method: .post, path: "\(apiPrefix)/scans", body: body, isIdempotent: false)
    }

    static func assessment(scanID: String) -> Endpoint<Report> {
        Endpoint(method: .get, path: "\(apiPrefix)/scans/\(scanID)/assessment", isIdempotent: true)
    }

    static func finishScan(scanID: String) -> Endpoint<Report> {
        Endpoint(method: .post, path: "\(apiPrefix)/scans/\(scanID)/finish", isIdempotent: false, timeout: finishTimeout)
    }

    /// Retried despite not being idempotent: a duplicate only leaves an unused open upload.
    static func createUpload(scanID: String, body: CreateUploadBody) -> Endpoint<UploadInfo> {
        Endpoint(method: .post, path: "\(apiPrefix)/scans/\(scanID)/uploads", body: body, isIdempotent: true)
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
