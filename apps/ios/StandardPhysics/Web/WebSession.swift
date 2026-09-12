import Foundation
import WebKit

struct WebSession {
    let cookie: HTTPCookie
    let origin: WebOrigin

    init(cookie: HTTPCookie, origin: WebOrigin) throws {
        self.cookie = cookie
        self.origin = origin
        guard isValid(for: origin) else { throw SessionError.invalidCookie }
    }

    func isValid(for origin: WebOrigin, now: Date = Date()) -> Bool {
        self.origin == origin && origin.scheme == "https"
            && cookie.domain.lowercased() == origin.host
            && cookie.isSecure && cookie.isHTTPOnly && cookie.path == "/"
            && !cookie.name.isEmpty && !cookie.value.isEmpty
            && cookie.expiresDate.map { $0 > now } == true
    }

    @MainActor
    func install(in store: WKHTTPCookieStore, origin: WebOrigin) async throws {
        guard isValid(for: origin) else { throw SessionError.invalidCookie }
        await store.setCookie(cookie)
        let installed = await store.allCookies()
        guard isValid(for: origin), installed.contains(where: {
            $0.name == cookie.name && $0.value == cookie.value && $0.path == cookie.path
                && $0.isSecure && $0.isHTTPOnly
        }) else { throw SessionError.invalidCookie }
    }

    enum SessionError: Error { case invalidCookie }
}
