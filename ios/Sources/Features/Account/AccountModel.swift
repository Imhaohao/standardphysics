import Foundation
import Observation

nonisolated protocol AccountService: Sendable {
    var sessionEnded: AsyncStream<Void> { get }
    func hasStoredSession() async -> Bool
    func signIn(email: String, password: String) async throws -> AuthSession
    func register(email: String, password: String) async throws -> AuthSession
    func signIn(appleIdentityToken: String, nonce: String) async throws -> AuthSession
    func currentUser() async throws -> ServerUser
    func signOut() async
    func deleteAccount() async throws
}

extension APIClient: AccountService {
    func hasStoredSession() async -> Bool { isSignedIn }
}

enum AccountState: Equatable {
    case signedOut
    case signedIn(email: String?)

    var isSignedIn: Bool { self != .signedOut }
}

enum EmailFormMode: Equatable {
    case signIn
    case register
}

/// Who is signed in. Scanning works the same either way; signing in only adds the server check.
@Observable
final class AccountModel {
    static let minimumPasswordLength = 8

    private(set) var state: AccountState = .signedOut
    private(set) var isWorking = false
    private(set) var errorMessage: String?
    /// Set when the server ended the session, so the account sheet opens to sign in again.
    var isSheetPresented = false

    @ObservationIgnored private let service: (any AccountService)?
    @ObservationIgnored private var sessionWatcher: Task<Void, Never>?
    /// Runs once the server has deleted the account, to clear what the phone kept from it.
    @ObservationIgnored var onAccountDeleted: (@MainActor () async -> Void)?

    var isAvailable: Bool { service != nil }

    init(service: (any AccountService)?, state: AccountState = .signedOut) {
        self.service = service
        self.state = state
        watchSession()
    }

    func restore() async {
        guard let service, await service.hasStoredSession() else { return }
        if !state.isSignedIn { state = .signedIn(email: nil) }
        guard let user = try? await service.currentUser() else { return }
        state = .signedIn(email: user.email)
    }

    func submitEmail(_ email: String, password: String, mode: EmailFormMode) async {
        let trimmed = email.trimmingCharacters(in: .whitespacesAndNewlines)
        if let problem = Self.formProblem(email: trimmed, password: password, mode: mode) {
            errorMessage = problem
            return
        }
        await run(failureContext: mode) { service in
            switch mode {
            case .signIn: try await service.signIn(email: trimmed, password: password)
            case .register: try await service.register(email: trimmed, password: password)
            }
        }
    }

    func signInWithApple(identityToken: Data?, nonce: AppleNonce?) async {
        guard let identityToken, let token = String(data: identityToken, encoding: .utf8), let nonce else {
            errorMessage = "Apple didn't send back a sign-in. Try again, or use your email instead."
            return
        }
        await run(failureContext: .signIn) { service in
            try await service.signIn(appleIdentityToken: token, nonce: nonce.raw)
        }
    }

    func appleSignInFailed(cancelled: Bool) {
        errorMessage = cancelled ? nil : "Sign in with Apple didn't finish. Try again, or use your email instead."
    }

    func signOut() async {
        guard let service else { return }
        isWorking = true
        await service.signOut()
        isWorking = false
        state = .signedOut
        errorMessage = nil
    }

    /// Deletes the account on the server for good, then signs out here. On failure the account
    /// and everything on the phone stay as they were.
    func deleteAccount() async {
        guard let service else { return }
        isWorking = true
        errorMessage = nil
        defer { isWorking = false }
        do {
            try await service.deleteAccount()
        } catch {
            errorMessage = (error as? APIError)?.userMessage ?? "We couldn't delete your account. Check your connection and try again."
            return
        }
        state = .signedOut
        isSheetPresented = false
        await onAccountDeleted?()
    }

    /// Freezes a state for previews and screenshots.
    func stage(_ state: AccountState) {
        self.state = state
    }

    func clearError() {
        errorMessage = nil
    }

    static func formProblem(email: String, password: String, mode: EmailFormMode) -> String? {
        guard email.contains("@"), email.contains(".") else { return "Enter your email address, like name@example.com." }
        guard !password.isEmpty else { return "Enter your password." }
        guard mode == .register, password.count < minimumPasswordLength else { return nil }
        return "Choose a password with at least \(minimumPasswordLength) characters."
    }

    static func message(for error: Error, mode: EmailFormMode) -> String {
        switch (error as? APIError, mode) {
        case (.unauthorized?, _): "That email and password don't match an account. Check them and try again."
        case (.conflict?, .register): "That email already has an account. Sign in with it instead."
        case (let apiError?, _): apiError.userMessage
        case (nil, _): "Signing in didn't work. Check your connection and try again."
        }
    }

    private func run(failureContext mode: EmailFormMode, _ work: (any AccountService) async throws -> AuthSession) async {
        guard let service else { return }
        isWorking = true
        errorMessage = nil
        defer { isWorking = false }
        do {
            let session = try await work(service)
            state = .signedIn(email: session.user.email)
            isSheetPresented = false
        } catch {
            errorMessage = Self.message(for: error, mode: mode)
        }
    }

    private func watchSession() {
        guard let stream = service?.sessionEnded else { return }
        sessionWatcher = Task { [weak self] in
            for await _ in stream {
                self?.sessionExpired()
            }
        }
    }

    private func sessionExpired() {
        guard state.isSignedIn else { return }
        state = .signedOut
        errorMessage = "Your session ended. Sign in again so new rooms keep going to the server."
        isSheetPresented = true
    }
}
