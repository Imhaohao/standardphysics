import Foundation

nonisolated protocol UploadAPI: Sendable {
    func createUpload(scanID: String, body: CreateUploadBody, idempotencyKey: String) async throws -> UploadInfo
    func uploadStatus(scanID: String, uploadID: String) async throws -> UploadStatusResponse
    func presignParts(scanID: String, uploadID: String, partNumbers: [Int]) async throws -> PresignResponse
    func completeUpload(scanID: String, uploadID: String, sha256: String) async throws -> Artifact
    func abortUpload(scanID: String, uploadID: String) async throws
}

nonisolated enum APIConfiguration {
    static let baseURLInfoKey = "SPAPIBaseURL"

    static func baseURL(in bundle: Bundle = .main) throws -> URL {
        guard let text = bundle.object(forInfoDictionaryKey: baseURLInfoKey) as? String else { throw APIError.notConfigured }
        return try validatedBaseURL(text)
    }

    static func validatedBaseURL(_ text: String, allowsLocalHTTP: Bool = TransportSecurity.isDebugBuild) throws -> URL {
        guard let url = URL(string: text), TransportSecurity.isAllowed(url, allowsLocalHTTP: allowsLocalHTTP) else {
            throw APIError.notConfigured
        }
        return url
    }
}

/// Everything leaves the phone over TLS. Debug builds may also talk plain HTTP to a server on
/// this Mac or the simulator's host, and nothing else.
nonisolated enum TransportSecurity {
    static let localHosts: Set<String> = ["localhost", "127.0.0.1", "::1"]

    static var isDebugBuild: Bool {
        #if DEBUG
        true
        #else
        false
        #endif
    }

    static func isAllowed(_ url: URL, allowsLocalHTTP: Bool = isDebugBuild) -> Bool {
        guard let scheme = url.scheme?.lowercased(), let host = url.host?.lowercased() else { return false }
        if scheme == "https" { return true }
        return allowsLocalHTTP && scheme == "http" && localHosts.contains(host)
    }
}

actor APIClient: UploadAPI {
    private let baseURL: URL
    private let tokenStore: any TokenStoring
    private let transport: any HTTPTransport
    private let retryPolicy: RetryPolicy
    private let sleep: Sleeper
    private let sessionEndedContinuation: AsyncStream<Void>.Continuation

    /// Yields when the server rejects the stored token. The token is already cleared by then.
    nonisolated let sessionEnded: AsyncStream<Void>

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
        (sessionEnded, sessionEndedContinuation) = AsyncStream.makeStream(of: Void.self, bufferingPolicy: .bufferingNewest(1))
    }

    static func fromInfoPlist(bundle: Bundle = .main) throws -> APIClient {
        APIClient(baseURL: try APIConfiguration.baseURL(in: bundle))
    }

    // MARK: Auth

    var isSignedIn: Bool { tokenStore.token() != nil }

    @discardableResult
    func signIn(email: String, password: String) async throws -> AuthSession {
        try await storeSession(from: APIRoutes.login(Credentials(email: email, password: password)))
    }

    @discardableResult
    func register(email: String, password: String) async throws -> AuthSession {
        try await storeSession(from: APIRoutes.register(Credentials(email: email, password: password)))
    }

    @discardableResult
    func signIn(appleIdentityToken: String, nonce: String) async throws -> AuthSession {
        let body = AppleSignInRequest(identityToken: appleIdentityToken, nonce: nonce)
        return try await storeSession(from: APIRoutes.signInWithApple(body))
    }

    /// The local token is cleared even when the server cannot be reached.
    func signOut() async {
        _ = try? await send(APIRoutes.logout())
        tokenStore.clear()
    }

    func currentUser() async throws -> ServerUser {
        try await send(APIRoutes.me())
    }

    /// The local token goes only once the server confirms the account is gone.
    func deleteAccount() async throws {
        _ = try await send(APIRoutes.deleteAccount())
        tokenStore.clear()
    }

    private func storeSession(from endpoint: Endpoint<AuthSession>) async throws -> AuthSession {
        let session = try await send(endpoint)
        try tokenStore.save(session.token)
        return session
    }

    // MARK: Scans

    func createScan(name: String?, siteName: String? = nil, idempotencyKey: String) async throws -> ScanResponse {
        try await send(APIRoutes.createScan(CreateScanRequest(name: name, siteName: siteName), idempotencyKey: idempotencyKey))
    }

    /// Runs the server's finish pipeline and returns the full report (can take up to two minutes).
    func finishScan(scanID: String) async throws -> Report {
        try await send(APIRoutes.finishScan(scanID: scanID))
    }

    func assessment(scanID: String) async throws -> Report {
        try await send(APIRoutes.assessment(scanID: scanID))
    }

    func listScans() async throws -> [ScanResponse] {
        try await send(APIRoutes.listScans())
    }

    func renameScan(scanID: String, name: String) async throws -> ScanResponse {
        try await send(APIRoutes.renameScan(scanID: scanID, body: RenameScanRequest(name: name)))
    }

    func deleteScan(scanID: String) async throws {
        _ = try await send(APIRoutes.deleteScan(scanID: scanID))
    }

    func uploadPhoto(jpeg: Data, scanID: String) async throws -> String {
        try await PhotoUploader(api: self, storage: URLSessionTransport()).upload(jpeg: jpeg, scanID: scanID)
    }

    func uploadCrop(jpeg: Data, scanID: String) async throws -> String {
        try await PhotoUploader(api: self, storage: URLSessionTransport()).upload(jpeg: jpeg, scanID: scanID, kind: .crop)
    }

    func answerFromPhoto(scanID: String, subjectID: String, metric: String, artifactID: String) async throws -> PhotoAnswerResponse {
        let body = PhotoAnswerRequest(subjectID: subjectID, metric: metric, artifactID: artifactID)
        return try await send(APIRoutes.photoAnswer(scanID: scanID, body: body))
    }

    func createShare(scanID: String) async throws -> ShareResponse {
        try await send(APIRoutes.createShare(scanID: scanID))
    }

    func answers(scanID: String) async throws -> [ServerAnswer] {
        try await send(APIRoutes.answers(scanID: scanID))
    }

    func saveAnswers(scanID: String, answers: [AnswerUpdate]) async throws -> Report {
        try await send(APIRoutes.saveAnswers(scanID: scanID, body: AnswersRequest(answers: answers)))
    }

    /// The scene as JSON text, in the shape `SceneSubjects` reads.
    func sceneJSON(scanID: String) async throws -> String {
        let scene = try await send(APIRoutes.scene(scanID: scanID))
        guard let text = String(data: try WireCoding.encoder().encode(scene), encoding: .utf8) else {
            throw APIError.malformedResponse
        }
        return text
    }

    // MARK: Uploads

    func createUpload(scanID: String, body: CreateUploadBody, idempotencyKey: String) async throws -> UploadInfo {
        try await send(APIRoutes.createUpload(scanID: scanID, body: body, idempotencyKey: idempotencyKey))
    }

    func uploadStatus(scanID: String, uploadID: String) async throws -> UploadStatusResponse {
        try await send(APIRoutes.uploadStatus(scanID: scanID, uploadID: uploadID))
    }

    func presignParts(scanID: String, uploadID: String, partNumbers: [Int]) async throws -> PresignResponse {
        let body = PresignRequest(partNumbers: partNumbers)
        return try await send(APIRoutes.presignParts(scanID: scanID, uploadID: uploadID, body: body))
    }

    func completeUpload(scanID: String, uploadID: String, sha256: String) async throws -> Artifact {
        let body = CompleteUploadRequest(sha256: sha256)
        return try await send(APIRoutes.completeUpload(scanID: scanID, uploadID: uploadID, body: body))
    }

    func abortUpload(scanID: String, uploadID: String) async throws {
        _ = try await send(APIRoutes.abortUpload(scanID: scanID, uploadID: uploadID))
    }

    // MARK: Live

    /// `wss` always; plain `ws` only for the local debug server `TransportSecurity` allows.
    func liveSocketRequest(scanID: String) throws -> URLRequest {
        guard TransportSecurity.isAllowed(baseURL) else { throw APIError.notConfigured }
        var components = try urlComponents(path: APIRoutes.livePath(scanID: scanID))
        components.scheme = components.scheme == "https" ? "wss" : "ws"
        guard let url = components.url else { throw APIError.notConfigured }
        var request = URLRequest(url: url)
        applyAuthorization(to: &request)
        return request
    }

    // MARK: Core

    func send<Response>(_ endpoint: Endpoint<Response>) async throws -> Response {
        let request = try buildRequest(endpoint)
        let response = try await performWithRetry(request, idempotent: endpoint.isIdempotent)
        if let empty = EmptyResponse() as? Response { return empty }
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
        guard response.isSuccess else {
            if response.status == 401, let sent = request.value(forHTTPHeaderField: "Authorization") { endSession(ifStillUsing: sent) }
            throw APIError(response: response)
        }
        return response
    }

    /// A slow request that fails after a fresh sign-in must not throw away the new session.
    private func endSession(ifStillUsing sentAuthorization: String) {
        guard let token = tokenStore.token(), sentAuthorization == "Bearer \(token)" else { return }
        tokenStore.clear()
        sessionEndedContinuation.yield()
    }

    private func buildRequest<Response>(_ endpoint: Endpoint<Response>) throws -> URLRequest {
        var components = try urlComponents(path: endpoint.path)
        if !endpoint.query.isEmpty { components.queryItems = endpoint.query }
        guard let url = components.url else { throw APIError.notConfigured }
        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let timeout = endpoint.timeout { request.timeoutInterval = timeout }
        for (name, value) in endpoint.headers { request.setValue(value, forHTTPHeaderField: name) }
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
