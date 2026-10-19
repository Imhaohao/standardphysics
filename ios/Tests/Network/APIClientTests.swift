import XCTest
@testable import StandardPhysics

final class RetryPolicyTests: XCTestCase {
    private func policy(jitter: Double) -> RetryPolicy {
        RetryPolicy(maxAttempts: 4, backoff: Backoff(base: .milliseconds(400), maximum: .seconds(1), jitter: { jitter }))
    }

    func testBackoffGrowsExponentiallyAndIsCapped() {
        let policy = policy(jitter: 1)
        let delays = (1...4).map { policy.delay(afterFailure: .offline, attemptsMade: $0, idempotent: true) }
        XCTAssertEqual(delays.prefix(3).map { $0 }, [.milliseconds(400), .milliseconds(800), .seconds(1)])
        XCTAssertNil(delays[3], "attempt budget exhausted")
    }

    func testJitterSpansHalfToFullCeiling() {
        XCTAssertEqual(policy(jitter: 0).delay(afterFailure: .offline, attemptsMade: 2, idempotent: true), .milliseconds(400))
        XCTAssertEqual(policy(jitter: 1).delay(afterFailure: .offline, attemptsMade: 2, idempotent: true), .milliseconds(800))
    }

    func testNonIdempotentCallsAreNeverRetried() {
        XCTAssertNil(policy(jitter: 0).delay(afterFailure: .server(status: 503, message: nil), attemptsMade: 1, idempotent: false))
    }

    func testPermanentErrorsAreNeverRetried() {
        for error: APIError in [.unauthorized, .forbidden, .notFound, .rejected(status: 400, message: nil), .malformedResponse] {
            XCTAssertNil(policy(jitter: 0).delay(afterFailure: error, attemptsMade: 1, idempotent: true), "\(error)")
        }
    }

    func testServerRetryAfterHintWinsWhenLonger() {
        let delay = policy(jitter: 0).delay(afterFailure: .rateLimited(retryAfter: 7), attemptsMade: 1, idempotent: true)
        XCTAssertEqual(delay, .seconds(7))
    }
}

final class APIClientTests: XCTestCase {
    private let baseURL = URL(string: "https://api.test")!

    private func makeClient(
        _ script: [Result<HTTPResponse, Error>], token: String? = "tok-1", sleeper: RecordingSleeper = RecordingSleeper()
    ) -> (APIClient, ScriptedTransport, InMemoryTokenStore, RecordingSleeper) {
        let transport = ScriptedTransport(script)
        let store = InMemoryTokenStore(token: token)
        let policy = RetryPolicy(maxAttempts: 3, backoff: Backoff(jitter: { 0 }))
        let client = APIClient(baseURL: baseURL, tokenStore: store, transport: transport, retryPolicy: policy, sleep: sleeper.sleeper)
        return (client, transport, store, sleeper)
    }

    private let scanJSON = #"{"id":"6f1c3a52-0000-4000-8000-000000000001","name":"Cafe","site_name":null,"status":"capturing","created_at":"2026-10-19T10:00:00.123456Z","updated_at":"2026-10-19T10:00:00Z"}"#
    private let authJSON = #"{"token":"fresh","expires_at":"2030-01-01T00:00:00Z","user":{"id":"u1","email":"a@b.co"}}"#

    func testCreateScanRetriesWithTheSameIdempotencyKey() async throws {
        let (retrying, retryingTransport, _, _) = makeClient([jsonResponse(503, "{}"), jsonResponse(201, scanJSON)])
        _ = try await retrying.createScan(name: "Cafe", idempotencyKey: "key-1")
        XCTAssertEqual(retryingTransport.requests.count, 2)
        XCTAssertEqual(retryingTransport.requests.map { $0.value(forHTTPHeaderField: "Idempotency-Key") }, ["key-1", "key-1"])

        let (client, transport, _, _) = makeClient([jsonResponse(201, scanJSON)])
        let scan = try await client.createScan(name: "Cafe", siteName: "Main St", idempotencyKey: "key-2")
        XCTAssertEqual(scan.status, "capturing")
        XCTAssertNil(scan.siteName)
        XCTAssertEqual(transport.requests[0].url?.path, "/v1/scans")
        XCTAssertEqual(transport.requests[0].value(forHTTPHeaderField: "Authorization"), "Bearer tok-1")
        let body = try JSONSerialization.jsonObject(with: transport.requests[0].httpBody!) as? [String: String]
        XCTAssertEqual(body, ["name": "Cafe", "site_name": "Main St"])
    }

    func testSignInStoresTokenAndSendsNoAuthorization() async throws {
        let (client, transport, store, _) = makeClient([jsonResponse(200, authJSON)], token: nil)
        let session = try await client.signIn(email: "a@b.co", password: "pw")
        XCTAssertEqual(store.token(), "fresh")
        XCTAssertEqual(session.user.email, "a@b.co")
        XCTAssertEqual(transport.requests[0].url?.path, "/v1/auth/login")
        XCTAssertNil(transport.requests[0].value(forHTTPHeaderField: "Authorization"))
        let body = try JSONSerialization.jsonObject(with: transport.requests[0].httpBody!) as? [String: String]
        XCTAssertEqual(body, ["email": "a@b.co", "password": "pw"])
    }

    func testSignInIsNotRetried() async {
        let (client, transport, _, _) = makeClient([jsonResponse(503, "{}")], token: nil)
        _ = try? await client.signIn(email: "a@b.co", password: "pw")
        XCTAssertEqual(transport.requests.count, 1)
    }

    func testRegisterAndAppleSignInUseSpecPathsAndBodies() async throws {
        let (client, transport, store, _) = makeClient([jsonResponse(201, authJSON), jsonResponse(200, authJSON)], token: nil)
        try await client.register(email: "a@b.co", password: "pw")
        try await client.signIn(appleIdentityToken: "jwt", nonce: "n1")
        XCTAssertEqual(store.token(), "fresh")
        XCTAssertEqual(transport.requests.map { $0.url?.path }, ["/v1/auth/register", "/v1/auth/apple"])
        let body = try JSONSerialization.jsonObject(with: transport.requests[1].httpBody!) as? [String: String]
        XCTAssertEqual(body, ["identity_token": "jwt", "nonce": "n1"])
    }

    func testSignOutPostsLogoutAndClearsTokenEvenWhenServerFails() async {
        let (client, transport, store, _) = makeClient([.failure(URLError(.notConnectedToInternet))] + Array(repeating: .failure(URLError(.notConnectedToInternet)), count: 2))
        await client.signOut()
        XCTAssertNil(store.token())
        XCTAssertEqual(transport.requests.first?.url?.path, "/v1/auth/logout")
    }

    func testRejectedTokenIsClearedAndEndsTheSession() async throws {
        let (client, _, store, _) = makeClient([jsonResponse(401, "{}")])
        var ended = client.sessionEnded.makeAsyncIterator()
        _ = try? await client.assessment(scanID: "s")
        XCTAssertNil(store.token())
        let signal: Void? = await ended.next()
        XCTAssertNotNil(signal)
    }

    func testWrongPasswordKeepsNoSessionSignal() async throws {
        let (client, _, store, _) = makeClient([jsonResponse(401, "{}")], token: "kept")
        _ = try? await client.signIn(email: "a@b.co", password: "nope")
        XCTAssertEqual(store.token(), "kept", "a failed login is not an expired session")
    }

    func testCurrentUserReadsMe() async throws {
        let (client, transport, _, _) = makeClient([jsonResponse(200, #"{"id":"u1","email":"a@b.co"}"#)])
        let user = try await client.currentUser()
        XCTAssertEqual(user, ServerUser(id: "u1", email: "a@b.co"))
        XCTAssertEqual(transport.requests[0].url?.path, "/v1/me")
    }

    func testNoContentResponsesNeedNoBody() async throws {
        let empty = Result<HTTPResponse, Error>.success(HTTPResponse(status: 204, headers: [:], body: Data()))
        let (client, transport, _, _) = makeClient([empty])
        try await client.abortUpload(scanID: "s", uploadID: "u")
        XCTAssertEqual(transport.requests[0].url?.path, "/v1/scans/s/uploads/u/abort")
    }

    func testErrorsMapToUserFacingMessages() async {
        let cases: [(Int, String, APIError)] = [
            (401, #"{"error":"unauthorized","message":"unauthorized"}"#, .unauthorized),
            (403, "{}", .forbidden),
            (404, #"{"error":"not_found","message":"not found"}"#, .notFound),
            (409, #"{"error":"conflict","message":"scan is already being finished"}"#, .conflict(message: "scan is already being finished")),
            (422, #"{"error":"unprocessable","message":"sha256 does not match the uploaded bytes"}"#, .rejected(status: 422, message: "sha256 does not match the uploaded bytes")),
        ]
        for (status, body, expected) in cases {
            let (client, _, _, _) = makeClient([jsonResponse(status, body)])
            do {
                _ = try await client.assessment(scanID: "s")
                XCTFail("expected failure for \(status)")
            } catch {
                XCTAssertEqual(error as? APIError, expected)
                XCTAssertFalse((error as? APIError)?.userMessage.isEmpty ?? true)
            }
        }
    }

    func testGETRetriesBadGatewayThenSucceeds() async throws {
        let (client, transport, _, sleeper) = makeClient([jsonResponse(502, #"{"error":"storage_error","message":"x"}"#), jsonResponse(200, reportJSON)])
        _ = try await client.assessment(scanID: "s")
        XCTAssertEqual(transport.requests.count, 2)
        XCTAssertEqual(sleeper.durations.count, 1)
    }

    func testOfflineTransportErrorIsRetriedThenSurfaced() async {
        let offline = Result<HTTPResponse, Error>.failure(URLError(.notConnectedToInternet))
        let (client, transport, _, _) = makeClient([offline, offline, offline])
        do {
            _ = try await client.assessment(scanID: "s")
            XCTFail("expected failure")
        } catch {
            XCTAssertEqual(error as? APIError, .offline)
        }
        XCTAssertEqual(transport.requests.count, 3)
    }

    private let reportJSON = """
    {"scan_id":"6f1c3a52-0000-4000-8000-000000000001","assessment_id":"a1","created_at":"2026-10-19T10:00:00.123456Z",
     "labelled_by_vision":2,"unlabelled_objects":1,
     "timings":{"load_ms":1,"labelling_ms":2,"evaluation_ms":3,"persist_ms":4,"total_ms":10},
     "summary":{"total":{"pass":1,"fail":1,"needs_info":1,"not_applicable":0},
       "by_jurisdiction":{"ADA2010":{"pass":1,"fail":0,"needs_info":0,"not_applicable":0}},
       "governing":[{"subject_id":"door-1","status":"fail","governing_rule_id":"CBC11B-404","governing_jurisdiction":"CBC11B","rule_ids":["ADA-404","CBC11B-404"],"message":"Stricter"}],
       "governing_counts":{"pass":0,"fail":1,"needs_info":0,"not_applicable":0}},
     "findings":[
      {"rule_id":"CBC11B-404.2.3","jurisdiction":"CBC11B","section":"404.2.3","title":"Door clear width","subject_id":"door-1","room_id":"room-1",
       "status":"fail","severity":"high","measured":{"text":"0.78 m","value":0.78,"lo":null,"hi":null,"unit":"m"},"required":">= 0.815 m",
       "message":"Too narrow","evidence":"measured","location":{"x":1,"y":0,"z":2},"counterpart":null},
      {"rule_id":"label.unresolved","jurisdiction":"SYSTEM","section":"","title":"Unlabelled object","subject_id":"obj-9","room_id":null,
       "status":"needs_info","severity":"low","measured":null,"required":"","message":"Could not label","evidence":"","location":null,"counterpart":null}]}
    """

    func testReportDecodesServerShapeIncludingMicrosecondDatesAndSystemFindings() async throws {
        let (client, transport, _, _) = makeClient([jsonResponse(200, reportJSON)])
        let report = try await client.assessment(scanID: "s1")
        XCTAssertEqual(transport.requests[0].url?.path, "/v1/scans/s1/assessment")
        XCTAssertEqual(report.findings.count, 2)
        XCTAssertEqual(report.findings[0].title, "Door clear width")
        XCTAssertEqual(report.findings[0].location, Point3(x: 1, y: 0, z: 2))
        XCTAssertEqual(report.summary.governing?.first?.governingJurisdiction, "CBC11B")
        XCTAssertEqual(report.summary.governingCounts?.fail, 1)
        XCTAssertEqual(report.timings.totalMs, 10)
        XCTAssertGreaterThan(report.createdAt.timeIntervalSince1970, 1_700_000_000)
        XCTAssertEqual(report.findings[0].asFinding?.measured, MeasuredValue(value: 0.78, unit: "m"))
        XCTAssertEqual(report.findings[0].asFinding?.required, ">= 0.815 m")
        XCTAssertNil(report.findings[1].asFinding, "SYSTEM findings have no shared type")
    }

    func testFinishScanUsesLongTimeoutAndIsNotRetried() async throws {
        let (failing, failingTransport, _, _) = makeClient([jsonResponse(500, "{}")])
        _ = try? await failing.finishScan(scanID: "s")
        XCTAssertEqual(failingTransport.requests.count, 1)

        let (client, transport, _, _) = makeClient([jsonResponse(200, reportJSON)])
        _ = try await client.finishScan(scanID: "s")
        XCTAssertEqual(transport.requests[0].url?.path, "/v1/scans/s/finish")
        XCTAssertEqual(transport.requests[0].timeoutInterval, 120)
    }

    func testUnreadableSuccessBodyIsMalformedResponse() async {
        let (client, _, _, _) = makeClient([jsonResponse(200, "<html>")])
        do {
            _ = try await client.assessment(scanID: "s")
            XCTFail("expected failure")
        } catch {
            XCTAssertEqual(error as? APIError, .malformedResponse)
        }
    }

    func testCreateUploadSendsSpecBodyAndDecodesUpload() async throws {
        let json = #"{"id":"u1","scan_id":"s","kind":"room","filename":"r.json","content_type":"application/json","size_bytes":10,"part_size":8388608,"part_count":1,"state":"open","created_at":"2026-10-19T10:00:00Z"}"#
        let (client, transport, _, _) = makeClient([jsonResponse(201, json)])
        let upload = try await client.createUpload(
            scanID: "s", body: CreateUploadBody(kind: "room", filename: "r.json", contentType: "application/json", sizeBytes: 10, partSize: 8_388_608),
            idempotencyKey: "upload-key"
        )
        XCTAssertEqual(upload.partCount, 1)
        XCTAssertEqual(transport.requests[0].value(forHTTPHeaderField: "Idempotency-Key"), "upload-key")
        XCTAssertEqual(transport.requests[0].url?.path, "/v1/scans/s/uploads")
        let body = String(decoding: transport.requests[0].httpBody!, as: UTF8.self)
        XCTAssertEqual(body, #"{"content_type":"application\/json","filename":"r.json","kind":"room","part_size":8388608,"size_bytes":10}"#)
    }

    func testPresignDecodesHeaderPairsAndExpiry() async throws {
        let json = #"{"expires_in_secs":3600,"parts":[{"part_number":2,"url":"https://r2.test/p2?sig=1","headers":[["host","r2.test"],["x-amz-checksum","abc"]]}]}"#
        let (client, transport, _, _) = makeClient([jsonResponse(200, json)])
        let response = try await client.presignParts(scanID: "s", uploadID: "u", partNumbers: [2])
        XCTAssertEqual(response.expiresInSecs, 3600)
        XCTAssertEqual(response.parts[0].headers, ["host": "r2.test", "x-amz-checksum": "abc"])
        XCTAssertEqual(transport.requests[0].url?.path, "/v1/scans/s/uploads/u/parts")
        XCTAssertEqual(String(decoding: transport.requests[0].httpBody!, as: UTF8.self), #"{"part_numbers":[2]}"#)
    }

    func testUploadStatusAndCompleteMatchSpec() async throws {
        let status = #"{"upload":{"id":"u","scan_id":"s","kind":"room","filename":"r","content_type":"x","size_bytes":10,"part_size":5,"part_count":2,"state":"open","created_at":"2026-10-19T10:00:00Z"},"uploaded_parts":[{"part_number":1,"etag":"\"e\"","size_bytes":5}]}"#
        let artifact = #"{"id":"a","scan_id":"s","upload_id":"u","kind":"room","filename":"r","content_type":"x","size_bytes":10,"sha256":"ff","created_at":"2026-10-19T10:00:00Z"}"#
        let (client, transport, _, _) = makeClient([jsonResponse(200, status), jsonResponse(200, artifact)])
        let current = try await client.uploadStatus(scanID: "s", uploadID: "u")
        XCTAssertEqual(current.uploadedParts, [UploadedPart(partNumber: 1, etag: "\"e\"", sizeBytes: 5)])
        let done = try await client.completeUpload(scanID: "s", uploadID: "u", sha256: "ff")
        XCTAssertEqual(done.sha256, "ff")
        XCTAssertEqual(String(decoding: transport.requests[1].httpBody!, as: UTF8.self), #"{"sha256":"ff"}"#)
        XCTAssertEqual(transport.requests[1].url?.path, "/v1/scans/s/uploads/u/complete")
    }

    func testLiveSocketRequestUsesWebSocketSchemeAndBearerHeader() async throws {
        let (client, _, _, _) = makeClient([])
        let request = try await client.liveSocketRequest(scanID: "s1")
        XCTAssertEqual(request.url?.absoluteString, "wss://api.test/v1/scans/s1/live")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer tok-1")
    }

    func testBaseURLReadFromBundleInfoDictionary() throws {
        XCTAssertThrowsError(try APIConfiguration.baseURL(in: Bundle(for: APIClientTests.self))) { error in
            XCTAssertEqual(error as? APIError, .notConfigured)
        }
    }
}

final class URLSessionTransportTests: XCTestCase {
    func testLowercasesHeadersAndReturnsStatusAndBody() async throws {
        StubURLProtocol.respond = { _ in (201, ["ETag": "\"abc\"", "Retry-After": "3"], Data("{}".utf8)) }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        let transport = URLSessionTransport(session: URLSession(configuration: configuration))
        let response = try await transport.send(URLRequest(url: URL(string: "https://stub.test/x")!))
        XCTAssertEqual(response.status, 201)
        XCTAssertEqual(response.headers["etag"], "\"abc\"")
        XCTAssertEqual(response.headers["retry-after"], "3")
        XCTAssertEqual(response.body, Data("{}".utf8))
    }
}

final class StubURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var respond: (@Sendable (URLRequest) -> (Int, [String: String], Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let (status, headers, body) = Self.respond?(request) ?? (500, [:], Data())
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: headers)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

final class KeychainTokenStoreTests: XCTestCase {
    func testSaveReadOverwriteAndClear() throws {
        let store = KeychainTokenStore(service: "sp.tests.\(UUID().uuidString)", account: "token")
        defer { store.clear() }
        XCTAssertNil(store.token())
        try store.save("one")
        XCTAssertEqual(store.token(), "one")
        try store.save("two")
        XCTAssertEqual(store.token(), "two")
        store.clear()
        XCTAssertNil(store.token())
    }
}
