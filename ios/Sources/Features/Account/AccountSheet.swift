import AuthenticationServices
import SwiftUI

struct AccountSheet: View {
    let account: AccountModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            PaperBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(account.state.isSignedIn ? "Your account" : "Sign in")
                            .font(Theme.Typography.title)
                            .foregroundStyle(Theme.Palette.ink)
                            .accessibilityAddTraits(.isHeader)
                        Spacer()
                        Button("Close") { dismiss() }
                            .buttonStyle(InkButtonStyle(variant: .quiet, height: Theme.Size.compactControl))
                    }
                    if case .signedIn(let email) = account.state {
                        SignedInPanel(account: account, email: email)
                    } else {
                        SignedOutPanel(account: account)
                    }
                }
                .padding(Theme.Spacing.m)
                .frame(maxWidth: Theme.Size.readable, alignment: .leading)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .disabled(account.isWorking)
        .onDisappear { account.clearError() }
    }
}

private struct SignedInPanel: View {
    let account: AccountModel
    let email: String?

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l) {
            Card(variant: .raised) {
                HStack(spacing: Theme.Spacing.s + 4) {
                    Image(systemName: "person.crop.circle.fill")
                        .font(.title2)
                        .foregroundStyle(Theme.Palette.pass)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Signed in")
                            .font(Theme.Typography.callout)
                            .foregroundStyle(Theme.Palette.inkMuted)
                        Text(email ?? "With your Apple Account")
                            .font(Theme.Typography.headline)
                            .foregroundStyle(Theme.Palette.ink)
                            .textSelection(.enabled)
                    }
                }
                .accessibilityElement(children: .combine)
            }
            Text("Scans you start now send each finished room to Standard Physics, so the full check is ready shortly after you tap Finish. Scans you started while signed out are checked on this phone.")
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Palette.inkMuted)
                .fixedSize(horizontal: false, vertical: true)
            SecondaryButton(title: "Sign out", systemImage: "rectangle.portrait.and.arrow.right") {
                Task { await account.signOut() }
            }
        }
    }
}

private struct SignedOutPanel: View {
    let account: AccountModel
    @State private var email = ""
    @State private var password = ""
    @State private var mode = EmailFormMode.signIn
    @State private var appleNonce: AppleNonce?

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l) {
            Text("Signing in sends each room to Standard Physics while you scan, so your full report is ready a few seconds after you finish. You can keep scanning without an account, and we'll check everything on this phone instead.")
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Palette.inkMuted)
                .fixedSize(horizontal: false, vertical: true)
            appleButton
            emailForm
            if let message = account.errorMessage {
                Label(message, systemImage: "exclamationmark.circle.fill")
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Palette.problem)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.updatesFrequently)
            }
        }
    }

    private var appleButton: some View {
        SignInWithAppleButton(.signIn) { request in
            appleNonce = try? AppleNonce.make()
            request.requestedScopes = [.email]
            request.nonce = appleNonce?.hashed
        } onCompletion: { result in
            handleApple(result)
        }
        .signInWithAppleButtonStyle(.black)
        .frame(height: Theme.Size.control)
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
    }

    private var emailForm: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            Text("Or use your email")
                .font(Theme.Typography.headline)
                .foregroundStyle(Theme.Palette.ink)
            InkTextField(label: "Email", text: $email, prompt: "name@example.com")
            InkTextField(
                label: "Password", text: $password, kind: mode == .register ? .newPassword : .password,
                prompt: mode == .register ? "At least \(AccountModel.minimumPasswordLength) characters" : nil
            )
            PrimaryButton(title: mode == .register ? "Create account" : "Sign in with email") {
                Task { await account.submitEmail(email, password: password, mode: mode) }
            }
            Button(mode == .register ? "I already have an account" : "Create an account instead") {
                mode = mode == .register ? .signIn : .register
                account.clearError()
            }
            .buttonStyle(InkButtonStyle(variant: .quiet, height: Theme.Size.compactControl))
            .frame(maxWidth: .infinity)
        }
    }

    private func handleApple(_ result: Result<ASAuthorization, Error>) {
        switch result {
        case .success(let authorization):
            let credential = authorization.credential as? ASAuthorizationAppleIDCredential
            let nonce = appleNonce
            Task { await account.signInWithApple(identityToken: credential?.identityToken, nonce: nonce) }
        case .failure(let error):
            account.appleSignInFailed(cancelled: (error as? ASAuthorizationError)?.code == .canceled)
        }
    }
}

#Preview("Signed out") {
    AccountSheet(account: AccountModel(service: nil))
}

#Preview("Signed in") {
    AccountSheet(account: AccountModel(service: nil, state: .signedIn(email: "owner@cornerdeli.com")))
}
