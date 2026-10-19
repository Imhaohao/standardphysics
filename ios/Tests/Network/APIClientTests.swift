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
    private let clientID = UUID(uuidString: "11111111-2222-3333-4444-555555555555")!

    private func makeClient(
        _ script: [Result<HTTPResponse, Error>], token: String? = "tok-1", sleeper: RecordingSleeper = RecordingSleeper()
    ) -> (APIClient, ScriptedTransport, InMemoryTokenStore, RecordingSleeper) {
        let transport = ScriptedTransport(script)
        let store = InMemoryTokenStore(token: token)
        let policy = RetryPolicy(maxAttempts: 3, backoff: Backoff(jitter: { 0 }))
        let client = APIClient(baseURL: baseURL, tokenStore: store, transport: transport, retryPolicy: policy, sleep: sleeper.sleeper)
        return (client, transport, store, sleeper)
    }

    private let scanJSON = #"{"id":"scan-9","client_id":"11111111-2222-3333-4444-555555555555","name":"Cafe","status":"open"}"#

    func testCreateScanRetriesTransientFailureWithSameIdempotencyKey() async throws {
        let (client, transport, _, sleeper) = makeClient([jsonResponse(503, "{}"), jsonResponse(200, scanJSON)])
        let scan = try await client.createScan(clientID: clientID, name: "Cafe")
        XCTAssertEqual(scan.id, "scan-9")
        XCTAssertEqual(transport.requests.count, 2)
        XCTAssertEqual(sleeper.durations.count, 1)
        for request in transport.requests {
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), clientID.uuidString)
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer tok-1")
            XCTAssertEqual(request.url?.path, "/v1/scans")
        }
    }

    func testSignInIsNotRetriedAndStoresTokenOnSuccess() async throws {
        let (failing, failingTransport, _, _) = makeClient([jsonResponse(503, "{}")], token: nil)
        do {
            _ = try await failing.signIn(email: "a@b.co", password: "pw")
            XCTFail("expected failure")
        } catch {
            XCTAssertEqual(error as? APIError, .server(status: 503, message: nil))
        }
        XCTAssertEqual(failingTransport.requests.count, 1)

        let (client, transport, store, _) = makeClient([jsonResponse(200, #"{"access_token":"fresh","expires_at":"2030-01-01T00:00:00Z"}"#)], token: nil)
        try await client.signIn(email: "a@b.co", password: "pw")
        XCTAssertEqual(store.token(), "fresh")
        XCTAssertNil(transport.requests[0].value(forHTTPHeaderField: "Authorization"))
        let body = try JSONSerialization.jsonObject(with: transport.requests[0].httpBody!) as? [String: String]
        XCTAssertEqual(body, ["email": "a@b.co", "password": "pw"])
    }

    func testAppleSignInSendsSnakeCaseBody() async throws {
        let (client, transport, store, _) = makeClient([jsonResponse(200, #"{"access_token":"apple-token"}"#)], token: nil)
        try await client.signIn(appleIdentityToken: "jwt", fullName: "Pat Lee")
        XCTAssertEqual(store.token(), "apple-token")
        XCTAssertEqual(transport.requests[0].url?.path, "/v1/auth/apple")
        let body = try JSONSerialization.jsonObject(with: transport.requests[0].httpBody!) as? [String: String]
        XCTAssertEqual(body, ["identity_token": "jwt", "full_name": "Pat Lee"])
    }

    func testErrorsMapToUserFacingMessages() async {
        let cases: [(Int, String, APIError)] = [
            (401, "{}", .unauthorized),
            (403, "{}", .forbidden),
            (404, "{}", .notFound),
            (409, #"{"message":"Scan already finished"}"#, .conflict(message: "Scan already finished")),
            (422, #"{"message":"Bad part"}"#, .rejected(status: 422, message: "Bad part")),
        ]
        for (status, body, expected) in cases {
            let (client, _, _, _) = makeClient([jsonResponse(status, body)])
            do {
                _ = try await client.findings(scanID: "s")
                XCTFail("expected failure for \(status)")
            } catch {
                XCTAssertEqual(error as? APIError, expected)
                XCTAssertFalse((error as? APIError)?.userMessage.isEmpty ?? true)
            }
        }
    }

    func testOfflineTransportErrorIsRetriedThenSurfaced() async {
        let offline = Result<HTTPResponse, Error>.failure(URLError(.notConnectedToInternet))
        let (client, transport, _, _) = makeClient([offline, offline, offline])
        do {
            _ = try await client.completeScan(scanID: "s")
            XCTFail("expected failure")
        } catch {
            XCTAssertEqual(error as? APIError, .offline)
        }
        XCTAssertEqual(transport.requests.count, 3)
    }

    func testRateLimitHonorsRetryAfter() async throws {
        let limited = jsonResponse(429, "{}", headers: ["retry-after": "9"])
        let (client, _, _, sleeper) = makeClient([limited, jsonResponse(200, #"{"job_id":"j","status":"queued"}"#)])
        let result = try await client.completeScan(scanID: "s")
        XCTAssertEqual(result.jobID, "j")
        XCTAssertEqual(sleeper.durations, [.seconds(9)])
    }

    func testFindingsDecodeSharedContractShape() async throws {
        let json = """
        {"status":"processing","last_event_id":12,"findings":[{"rule_id":"CBC11B-404.2.3","jurisdiction":"CBC11B",
        "section":"404.2.3","subject_id":"door-1","status":"needs_info","measured":{"value":0.78,"unit":"m"},
        "required":">= 0.815 m","message":"Clear width unknown","evidence":"measured"}]}
        """
        let (client, transport, _, _) = makeClient([jsonResponse(200, json)])
        let response = try await client.findings(scanID: "s1", afterEventID: 7)
        XCTAssertEqual(response.lastEventID, 12)
        XCTAssertEqual(response.findings.first?.status, .needsInfo)
        XCTAssertEqual(response.findings.first?.measured, MeasuredValue(value: 0.78, unit: "m"))
        XCTAssertEqual(transport.requests[0].url?.query, "after=7")
    }

    func testUnreadableSuccessBodyIsMalformedResponse() async {
        let (client, _, _, _) = makeClient([jsonResponse(200, "<html>")])
        do {
            _ = try await client.createScan(clientID: clientID, name: "x")
            XCTFail("expected failure")
        } catch {
            XCTAssertEqual(error as? APIError, .malformedResponse)
        }
    }

    func testCompleteUploadSendsSortedSnakeCaseParts() async throws {
        let (client, transport, _, _) = makeClient([jsonResponse(200, #"{"file_key":"k"}"#)])
        try await client.completeUpload(
            scanID: "s", uploadID: "u",
            parts: [CompletedPart(partNumber: 2, etag: "\"b\""), CompletedPart(partNumber: 1, etag: "\"a\"")]
        )
        XCTAssertEqual(transport.requests[0].url?.path, "/v1/scans/s/uploads/u/complete")
        let body = String(decoding: transport.requests[0].httpBody!, as: UTF8.self)
        XCTAssertEqual(body, #"{"parts":[{"etag":"\"a\"","part_number":1},{"etag":"\"b\"","part_number":2}]}"#)
    }

    func testRequestUploadDecodesGrantWithFractionalSecondDates() async throws {
        let json = #"{"upload_id":"u1","part_size":8388608,"parts":[{"part_number":1,"url":"https://r2.test/p1","expires_at":"2030-01-01T00:00:00.250Z"}]}"#
        let (client, _, _, _) = makeClient([jsonResponse(200, json)])
        let body = RequestUploadBody(fileName: "a.json", contentType: "application/json", sizeBytes: 10, partSize: 8_388_608)
        let grant = try await client.requestUpload(scanID: "s", file: body, clientFileID: clientID)
        XCTAssertEqual(grant.uploadID, "u1")
        XCTAssertEqual(grant.parts[0].url.absoluteString, "https://r2.test/p1")
    }

    func testLiveSocketRequestUsesWebSocketSchemeTokenAndResumePoint() async throws {
        let (client, _, _, _) = makeClient([])
        let request = try await client.liveSocketRequest(scanID: "s1", lastEventID: 42)
        XCTAssertEqual(request.url?.absoluteString, "wss://api.test/v1/scans/s1/live?last_event_id=42")
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
