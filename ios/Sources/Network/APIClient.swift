import Foundation

nonisolated protocol UploadAPI: Sendable {
    func requestUpload(scanID: String, file: RequestUploadBody, clientFileID: UUID) async throws -> MultipartUploadGrant
    func refreshPartURLs(scanID: String, uploadID: String, partNumbers: [Int]) async throws -> [PresignedPart]
    func completeUpload(scanID: String, uploadID: String, parts: [CompletedPart]) async throws
}

nonisolated enum APIConfiguration {
    static let baseURLInfoKey = "SPAPIBaseURL"

    static func baseURL(in bundle: Bundle = .main) throws -> URL {
        guard let text = bundle.object(forInfoDictionaryKey: baseURLInfoKey) as? String,
              let url = URL(string: text), url.host != nil else { throw APIError.notConfigured }
        return url
    }
}

actor APIClient: UploadAPI {
    private let baseURL: URL
    private let tokenStore: any TokenStoring
    private let transport: any HTTPTransport
    private let retryPolicy: RetryPolicy
    private let sleep: Sleeper

    init(
        baseURL: URL,
        tokenStore: any TokenStoring = KeychainTokenStore(),
        transport: any HTTPTransport = URLSessionTransport(),
        retryPolicy: RetryPolicy = RetryPolicy(),
        sleep: @escaping Sleeper = DefaultSleeper.sleep
    ) {
        self.baseURL = baseURL
        self.tokenStore = tokenStore
        self.transport = transport
        self.retryPolicy = retryPolicy
        self.sleep = sleep
    }

    static func fromInfoPlist(bundle: Bundle = .main) throws -> APIClient {
        APIClient(baseURL: try APIConfiguration.baseURL(in: bundle))
    }

    // MARK: Auth

    var isSignedIn: Bool { tokenStore.token() != nil }

    @discardableResult
    func signIn(email: String, password: String) async throws -> AuthSession {
        try await storeSession(from: APIRoutes.signIn(SignInRequest(email: email, password: password)))
    }

    @discardableResult
    func signIn(appleIdentityToken: String, fullName: String?) async throws -> AuthSession {
        let body = AppleSignInRequest(identityToken: appleIdentityToken, fullName: fullName)
        return try await storeSession(from: APIRoutes.signInWithApple(body))
    }

    func signOut() {
        tokenStore.clear()
    }

    private func storeSession(from endpoint: Endpoint<AuthSession>) async throws -> AuthSession {
        let session = try await send(endpoint)
        try tokenStore.save(session.accessToken)
        return session
    }

    // MARK: Scans

    func createScan(clientID: UUID, name: String) async throws -> ScanResponse {
        try await send(APIRoutes.createScan(CreateScanRequest(clientID: clientID.uuidString, name: name)))
    }

    func completeScan(scanID: String) async throws -> CompleteScanResponse {
        try await send(APIRoutes.completeScan(scanID: scanID))
    }

    func findings(scanID: String, afterEventID: Int? = nil) async throws -> FindingsResponse {
        try await send(APIRoutes.findings(scanID: scanID, afterEventID: afterEventID))
    }

    // MARK: Uploads

    func requestUpload(scanID: String, file: RequestUploadBody, clientFileID: UUID) async throws -> MultipartUploadGrant {
        try await send(APIRoutes.requestUpload(scanID: scanID, body: file, clientFileID: clientFileID))
    }

    func refreshPartURLs(scanID: String, uploadID: String, partNumbers: [Int]) async throws -> [PresignedPart] {
        let body = RefreshPartsRequest(partNumbers: partNumbers)
        return try await send(APIRoutes.refreshParts(scanID: scanID, uploadID: uploadID, body: body)).parts
    }

    func completeUpload(scanID: String, uploadID: String, parts: [CompletedPart]) async throws {
        let body = CompleteUploadRequest(parts: parts.sorted { $0.partNumber < $1.partNumber })
        _ = try await send(APIRoutes.completeUpload(scanID: scanID, uploadID: uploadID, body: body))
    }

    // MARK: Live

    func liveSocketRequest(scanID: String, lastEventID: Int?) throws -> URLRequest {
        var components = try urlComponents(path: APIRoutes.livePath(scanID: scanID))
        components.scheme = components.scheme == "https" ? "wss" : "ws"
        if let lastEventID {
            components.queryItems = [URLQueryItem(name: APIRoutes.lastEventIDQueryItem, value: String(lastEventID))]
        }
        guard let url = components.url else { throw APIError.notConfigured }
        var request = URLRequest(url: url)
        applyAuthorization(to: &request)
        return request
    }

    // MARK: Core

    func send<Response>(_ endpoint: Endpoint<Response>) async throws -> Response {
        let request = try buildRequest(endpoint)
        let response = try await performWithRetry(request, idempotent: endpoint.isIdempotent)
        do {
            return try WireCoding.decoder().decode(Response.self, from: response.body)
        } catch {
            throw APIError.malformedResponse
        }
    }

    private func performWithRetry(_ request: URLRequest, idempotent: Bool) async throws -> HTTPResponse {
        var attemptsMade = 0
        while true {
            do {
                return try await perform(request)
            } catch {
                let apiError = (error as? APIError) ?? APIError(transportError: error)
                attemptsMade += 1
                guard let delay = retryPolicy.delay(afterFailure: apiError, attemptsMade: attemptsMade, idempotent: idempotent) else {
                    throw apiError
                }
                try await sleep(delay)
            }
        }
    }

    private func perform(_ request: URLRequest) async throws -> HTTPResponse {
        let response = try await transport.send(request)
        guard response.isSuccess else { throw APIError(response: response) }
        return response
    }

    private func buildRequest<Response>(_ endpoint: Endpoint<Response>) throws -> URLRequest {
        var components = try urlComponents(path: endpoint.path)
        if !endpoint.query.isEmpty { components.queryItems = endpoint.query }
        guard let url = components.url else { throw APIError.notConfigured }
        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let key = endpoint.idempotencyKey { request.setValue(key, forHTTPHeaderField: APIRoutes.idempotencyHeader) }
        if endpoint.requiresAuth { applyAuthorization(to: &request) }
        try attachBody(endpoint.body, to: &request)
        return request
    }

    private func attachBody(_ body: (any Encodable & Sendable)?, to request: inout URLRequest) throws {
        guard let body else { return }
        request.httpBody = try WireCoding.encoder().encode(body)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    }

    private func applyAuthorization(to request: inout URLRequest) {
        guard let token = tokenStore.token() else { return }
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    }

    private func urlComponents(path: String) throws -> URLComponents {
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            throw APIError.notConfigured
        }
        components.path = path
        return components
    }
}
