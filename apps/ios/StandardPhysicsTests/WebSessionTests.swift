import WebKit
import XCTest
@testable import StandardPhysics

final class WebSessionTests: XCTestCase {
    @MainActor
    func testInstallsValidatedCookieBeforeWorkspaceCanLoad() async throws {
        let origin = try XCTUnwrap(WebOrigin(url: URL(string: "https://workspace.example")!))
        let session = try WebSession(cookie: makeCookie(), origin: origin)
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        let webView = WKWebView(frame: .zero, configuration: configuration)
        defer { withExtendedLifetime(webView) {} }
        let store = webView.configuration.websiteDataStore.httpCookieStore
        try await session.install(in: store, origin: origin)
        let cookies = await store.allCookies()
        XCTAssertTrue(cookies.contains { $0.name == "session" && $0.value == "test-session" })
    }

    func testRejectsExpiredInsecureAndCrossHostCookies() throws {
        let origin = try XCTUnwrap(WebOrigin(url: URL(string: "https://workspace.example")!))
        XCTAssertThrowsError(try WebSession(cookie: makeCookie(domain: "other.example"), origin: origin))
        XCTAssertThrowsError(try WebSession(cookie: makeCookie(domain: ".workspace.example"), origin: origin))
        XCTAssertThrowsError(try WebSession(cookie: makeCookie(expires: .distantPast), origin: origin))
        XCTAssertThrowsError(try WebSession(cookie: makeCookie(secure: false), origin: origin))
        XCTAssertThrowsError(try WebSession(cookie: makeCookie(httpOnly: false), origin: origin))
    }

    private func makeCookie(domain: String = "workspace.example", expires: Date = .distantFuture,
                            secure: Bool = true, httpOnly: Bool = true) -> HTTPCookie {
        var properties: [HTTPCookiePropertyKey: Any] = [
            .name: "session", .value: "test-session", .domain: domain, .path: "/", .expires: expires
        ]
        if secure { properties[.secure] = "TRUE" }
        if httpOnly { properties[HTTPCookiePropertyKey("HttpOnly")] = "TRUE" }
        return HTTPCookie(properties: properties)!
    }
}
