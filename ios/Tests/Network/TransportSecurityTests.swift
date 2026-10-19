import XCTest
@testable import StandardPhysics

final class TransportSecurityTests: XCTestCase {
    func testBaseURLMustBeHTTPS() throws {
        XCTAssertNoThrow(try APIConfiguration.validatedBaseURL("https://api.standardphysics.app", allowsLocalHTTP: false))
        XCTAssertThrowsError(try APIConfiguration.validatedBaseURL("http://api.standardphysics.app", allowsLocalHTTP: true))
        XCTAssertThrowsError(try APIConfiguration.validatedBaseURL("http://localhost:8080", allowsLocalHTTP: false))
        XCTAssertNoThrow(try APIConfiguration.validatedBaseURL("http://localhost:8080", allowsLocalHTTP: true))
        XCTAssertThrowsError(try APIConfiguration.validatedBaseURL("ftp://api.standardphysics.app", allowsLocalHTTP: true))
    }

    func testLiveSocketUsesWSSForAnHTTPSServer() async throws {
        let client = APIClient(baseURL: URL(string: "https://api.test")!, tokenStore: InMemoryTokenStore(token: "t"))
        let request = try await client.liveSocketRequest(scanID: "s1")
        XCTAssertEqual(request.url?.scheme, "wss")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer t")
        XCTAssertNil(request.url?.query, "the token never goes in the URL")
    }

    func testLiveSocketRefusesAnInsecureRemoteServer() async {
        let client = APIClient(baseURL: URL(string: "http://api.test")!, tokenStore: InMemoryTokenStore(token: "t"))
        do {
            _ = try await client.liveSocketRequest(scanID: "s1")
            XCTFail("expected refusal")
        } catch {
            XCTAssertEqual(error as? APIError, .notConfigured)
        }
    }

    func testRetryAfterIsCappedAtOneMinute() {
        XCTAssertEqual(APIError.retryAfter("5"), 5)
        XCTAssertEqual(APIError.retryAfter("86400"), 60)
        XCTAssertNil(APIError.retryAfter("-3"))
        XCTAssertNil(APIError.retryAfter(nil))
    }

    func testServerMessagesAreStrippedAndCapped() {
        XCTAssertEqual(ServerText.sanitized("bad\u{0007}\nvalue\t"), "badvalue")
        let long = ServerText.sanitized(String(repeating: "a", count: 500))
        XCTAssertEqual(long.count, ServerText.maximumLength)
        XCTAssertTrue(long.hasSuffix("…"))
    }

    func testErrorBodiesAreSanitizedBeforeDisplay() {
        let body = Data(#"{"error":"bad_request","message":"line one\u0000\u001b[31m"}"#.utf8)
        let error = APIError(response: HTTPResponse(status: 400, headers: [:], body: body))
        XCTAssertEqual(error, .rejected(status: 400, message: "line one[31m"))
    }

    func testResponsesPastTheLimitAreCutOff() async throws {
        let small = try await URLSessionTransport.collect(AsyncStream { continuation in
            [1, 2, 3].forEach { continuation.yield(UInt8($0)) }
            continuation.finish()
        }, limit: 3)
        XCTAssertEqual(small, Data([1, 2, 3]))
        do {
            _ = try await URLSessionTransport.collect(AsyncStream { continuation in
                (0..<4).forEach { continuation.yield(UInt8($0)) }
                continuation.finish()
            }, limit: 3)
            XCTFail("expected the cap to trip")
        } catch {
            XCTAssertEqual(error as? APIError, .responseTooLarge)
        }
    }
}
