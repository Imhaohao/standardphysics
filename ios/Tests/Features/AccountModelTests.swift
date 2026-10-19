import CryptoKit
import XCTest
@testable import StandardPhysics

final class AppleNonceTests: XCTestCase {
    func testNonceIsThirtyTwoRandomBytesInHex() throws {
        let first = try AppleNonce.make()
        let second = try AppleNonce.make()
        XCTAssertEqual(first.raw.count, AppleNonce.byteCount * 2)
        XCTAssertTrue(first.raw.allSatisfy(\.isHexDigit))
        XCTAssertNotEqual(first, second)
    }

    func testHashedIsSHA256OfRaw() {
        let nonce = AppleNonce(raw: "abc")
        XCTAssertEqual(nonce.hashed, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    }
}

@MainActor
final class AccountModelTests: XCTestCase {
    private final class FakeAccountService: AccountService, @unchecked Sendable {
        let sessionEnded: AsyncStream<Void>
        let endSession: AsyncStream<Void>.Continuation
        var storedSession = false
        var user = ServerUser(id: "u1", email: "owner@shop.com")
        var failure: APIError?
        private(set) var calls: [String] = []

        init() {
            (sessionEnded, endSession) = AsyncStream.makeStream(of: Void.self)
        }

        func hasStoredSession() async -> Bool { storedSession }

        func signIn(email: String, password: String) async throws -> AuthSession {
            calls.append("login \(email)")
            return try session()
        }

        func register(email: String, password: String) async throws -> AuthSession {
            calls.append("register \(email)")
            return try session()
        }

        func signIn(appleIdentityToken: String, nonce: String) async throws -> AuthSession {
            calls.append("apple \(appleIdentityToken) \(nonce)")
            return try session()
        }

        func currentUser() async throws -> ServerUser { user }
        func signOut() async { calls.append("logout") }

        private func session() throws -> AuthSession {
            if let failure { throw failure }
            return AuthSession(token: "t", expiresAt: .distantFuture, user: user)
        }
    }

    func testEmailSignInSignsInAndClosesTheSheet() async {
        let service = FakeAccountService()
        let account = AccountModel(service: service)
        account.isSheetPresented = true
        await account.submitEmail("  owner@shop.com ", password: "secret", mode: .signIn)
        XCTAssertEqual(account.state, .signedIn(email: "owner@shop.com"))
        XCTAssertFalse(account.isSheetPresented)
        XCTAssertEqual(service.calls, ["login owner@shop.com"])
    }

    func testRegisterChecksPasswordLengthBeforeCallingTheServer() async {
        let service = FakeAccountService()
        let account = AccountModel(service: service)
        await account.submitEmail("owner@shop.com", password: "short", mode: .register)
        XCTAssertEqual(account.errorMessage, "Choose a password with at least 8 characters.")
        XCTAssertTrue(service.calls.isEmpty)
    }

    func testWrongPasswordExplainsWhatToCheck() async {
        let service = FakeAccountService()
        service.failure = .unauthorized
        let account = AccountModel(service: service)
        await account.submitEmail("owner@shop.com", password: "secret", mode: .signIn)
        XCTAssertEqual(account.state, .signedOut)
        XCTAssertEqual(account.errorMessage, AccountModel.message(for: APIError.unauthorized, mode: .signIn))
    }

    func testTakenEmailSuggestsSigningIn() {
        XCTAssertEqual(
            AccountModel.message(for: APIError.conflict(message: "email is already registered"), mode: .register),
            "That email already has an account. Sign in with it instead."
        )
    }

    func testAppleSignInSendsTheRawNonce() async {
        let service = FakeAccountService()
        service.user = ServerUser(id: "u2", email: nil)
        let account = AccountModel(service: service)
        await account.signInWithApple(identityToken: Data("jwt".utf8), nonce: AppleNonce(raw: "raw-nonce"))
        XCTAssertEqual(service.calls, ["apple jwt raw-nonce"])
        XCTAssertEqual(account.state, .signedIn(email: nil))
    }

    func testAppleSignInWithoutATokenDoesNotCallTheServer() async {
        let service = FakeAccountService()
        let account = AccountModel(service: service)
        await account.signInWithApple(identityToken: nil, nonce: AppleNonce(raw: "n"))
        XCTAssertTrue(service.calls.isEmpty)
        XCTAssertNotNil(account.errorMessage)
    }

    func testCancelledAppleSignInShowsNoError() {
        let account = AccountModel(service: FakeAccountService())
        account.appleSignInFailed(cancelled: true)
        XCTAssertNil(account.errorMessage)
    }

    func testRestoreUsesTheStoredSessionAndFillsInTheEmail() async {
        let service = FakeAccountService()
        service.storedSession = true
        let account = AccountModel(service: service)
        await account.restore()
        XCTAssertEqual(account.state, .signedIn(email: "owner@shop.com"))
    }

    func testSignOutReturnsToSignedOut() async {
        let service = FakeAccountService()
        let account = AccountModel(service: service, state: .signedIn(email: "a@b.co"))
        await account.signOut()
        XCTAssertEqual(account.state, .signedOut)
        XCTAssertEqual(service.calls, ["logout"])
    }

    func testEndedSessionSignsOutAndOpensSignIn() async {
        let service = FakeAccountService()
        let account = AccountModel(service: service, state: .signedIn(email: "a@b.co"))
        service.endSession.yield()
        for _ in 0..<100 where account.state.isSignedIn {
            try? await Task.sleep(for: .milliseconds(5))
        }
        XCTAssertEqual(account.state, .signedOut)
        XCTAssertTrue(account.isSheetPresented)
        XCTAssertNotNil(account.errorMessage)
    }

    func testWithoutAServerSignInIsUnavailable() {
        XCTAssertFalse(AccountModel(service: nil).isAvailable)
    }
}
