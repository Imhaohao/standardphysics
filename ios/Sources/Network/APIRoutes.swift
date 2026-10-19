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
    var idempotencyKey: String?
}

/// The single place that knows server paths. Swapping to the generated OpenAPI contract
/// changes only this file and APIModels.swift.
nonisolated enum APIRoutes {
    static let apiPrefix = "/v1"
    static let idempotencyHeader = "Idempotency-Key"
    static let lastEventIDQueryItem = "last_event_id"

    static func signIn(_ body: SignInRequest) -> Endpoint<AuthSession> {
        Endpoint(method: .post, path: "\(apiPrefix)/auth/sign-in", body: body, requiresAuth: false, isIdempotent: false)
    }

    static func signInWithApple(_ body: AppleSignInRequest) -> Endpoint<AuthSession> {
        Endpoint(method: .post, path: "\(apiPrefix)/auth/apple", body: body, requiresAuth: false, isIdempotent: false)
    }

    static func createScan(_ body: CreateScanRequest) -> Endpoint<ScanResponse> {
        Endpoint(
            method: .post, path: "\(apiPrefix)/scans", body: body,
            isIdempotent: true, idempotencyKey: body.clientID
        )
    }

    static func requestUpload(scanID: String, body: RequestUploadBody, clientFileID: UUID) -> Endpoint<MultipartUploadGrant> {
        Endpoint(
            method: .post, path: "\(apiPrefix)/scans/\(scanID)/uploads", body: body,
            isIdempotent: true, idempotencyKey: clientFileID.uuidString
        )
    }

    static func refreshParts(scanID: String, uploadID: String, body: RefreshPartsRequest) -> Endpoint<PartsResponse> {
        Endpoint(
            method: .post, path: "\(apiPrefix)/scans/\(scanID)/uploads/\(uploadID)/parts/refresh",
            body: body, isIdempotent: true
        )
    }

    static func completeUpload(scanID: String, uploadID: String, body: CompleteUploadRequest) -> Endpoint<CompleteUploadResponse> {
        Endpoint(
            method: .post, path: "\(apiPrefix)/scans/\(scanID)/uploads/\(uploadID)/complete",
            body: body, isIdempotent: true
        )
    }

    static func completeScan(scanID: String) -> Endpoint<CompleteScanResponse> {
        Endpoint(method: .post, path: "\(apiPrefix)/scans/\(scanID)/complete", isIdempotent: true)
    }

    static func findings(scanID: String, afterEventID: Int?) -> Endpoint<FindingsResponse> {
        let query = afterEventID.map { [URLQueryItem(name: "after", value: String($0))] } ?? []
        return Endpoint(method: .get, path: "\(apiPrefix)/scans/\(scanID)/findings", query: query, isIdempotent: true)
    }

    static func livePath(scanID: String) -> String {
        "\(apiPrefix)/scans/\(scanID)/live"
    }
}
