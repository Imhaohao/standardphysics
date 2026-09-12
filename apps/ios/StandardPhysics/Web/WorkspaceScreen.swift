import SwiftUI
import WebKit

struct WorkspaceScreen: View {
    @ObservedObject var appModel: AppModel
    let scanID: UUID
    @State private var message: String?

    var body: some View {
        NavigationStack {
            Group {
                if let workspaceURL = AppEnvironment.workspaceBaseURL,
                   let origin = WebOrigin(url: workspaceURL),
                   let session = appModel.workspaceSession,
                   session.isValid(for: origin) {
                    WorkspaceWebView(
                        url: workspaceURL.appendingPathComponent("scans").appendingPathComponent(scanID.uuidString),
                        allowedOrigin: origin,
                        session: session,
                        onScanRequested: { appModel.beginCapture() },
                        onSessionExpired: {
                            appModel.workspaceSession = nil
                            message = "Sign in to your workspace to open this shop."
                        }
                    )
                } else {
                    VStack(spacing: AppTheme.Spacing.card) {
                        Text(message ?? "Connect your workspace to open this shop.")
                            .font(.title2)
                        Button("Connection") { appModel.screen = .connection }
                            .buttonStyle(AppButtonStyle())
                    }.padding(AppTheme.Spacing.page)
                }
            }
            .ignoresSafeArea(edges: .bottom)
            .navigationTitle("Your shop")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Shops") { appModel.showStart() }
                }
            }
        }
    }
}

struct WorkspaceWebView: UIViewRepresentable {
    let url: URL
    let allowedOrigin: WebOrigin
    let session: WebSession
    let onScanRequested: () -> Void
    let onSessionExpired: () -> Void

    init(url: URL, allowedOrigin: WebOrigin, session: WebSession,
         onScanRequested: @escaping () -> Void, onSessionExpired: @escaping () -> Void) {
        self.url = url
        self.allowedOrigin = allowedOrigin
        self.session = session
        self.onScanRequested = onScanRequested
        self.onSessionExpired = onSessionExpired
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(allowedOrigin: allowedOrigin, session: session,
            onScanRequested: onScanRequested, onSessionExpired: onSessionExpired)
    }

    func makeUIView(context: Context) -> WKWebView {
        let contentController = WKUserContentController()
        contentController.add(context.coordinator, name: "nativeCapture")
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.userContentController = contentController
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        context.coordinator.load(url, in: webView)
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        context.coordinator.load(url, in: webView)
    }

    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "nativeCapture")
        webView.navigationDelegate = nil
        coordinator.cancel()
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        private let allowedOrigin: WebOrigin
        private let session: WebSession
        private let onScanRequested: () -> Void
        private let onSessionExpired: () -> Void
        private var requestedURL: URL?
        private var loadTask: Task<Void, Never>?

        init(allowedOrigin: WebOrigin, session: WebSession,
             onScanRequested: @escaping () -> Void, onSessionExpired: @escaping () -> Void) {
            self.allowedOrigin = allowedOrigin
            self.session = session
            self.onScanRequested = onScanRequested
            self.onSessionExpired = onSessionExpired
        }

        func load(_ url: URL, in webView: WKWebView) {
            guard requestedURL != url, allowedOrigin.contains(url) else { return }
            requestedURL = url
            loadTask?.cancel()
            loadTask = Task { @MainActor [weak self, weak webView] in
                guard let self, let webView else { return }
                do {
                    try await session.install(in: webView.configuration.websiteDataStore.httpCookieStore,
                                              origin: allowedOrigin)
                    guard !Task.isCancelled else { return }
                    webView.load(URLRequest(url: url))
                } catch { onSessionExpired() }
            }
        }

        func cancel() {
            loadTask?.cancel()
            loadTask = nil
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse)
            async -> WKNavigationResponsePolicy {
            guard let response = navigationResponse.response as? HTTPURLResponse else { return .allow }
            if response.statusCode == 401 || response.statusCode == 403 {
                onSessionExpired()
                return .cancel
            }
            return .allow
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction
        ) async -> WKNavigationActionPolicy {
            guard let target = navigationAction.request.url else { return .cancel }
            guard session.isValid(for: allowedOrigin) else {
                onSessionExpired()
                return .cancel
            }
            if target.absoluteString == "about:blank" || allowedOrigin.contains(target) {
                return .allow
            } else {
                return .cancel
            }
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "nativeCapture",
                  session.isValid(for: allowedOrigin),
                  message.frameInfo.isMainFrame,
                  let sourceURL = message.frameInfo.request.url,
                  allowedOrigin.contains(sourceURL),
                  let action = message.body as? String,
                  action == "scanShop" else { return }
            DispatchQueue.main.async { self.onScanRequested() }
        }
    }
}

struct WebOrigin: Equatable, Sendable {
    let scheme: String
    let host: String
    let port: Int?

    init?(url: URL) {
        guard let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              let host = url.host?.lowercased() else { return nil }
        self.scheme = scheme
        self.host = host
        port = Self.effectivePort(for: url)
    }

    func contains(_ url: URL) -> Bool {
        url.scheme?.lowercased() == scheme
            && url.host?.lowercased() == host
            && Self.effectivePort(for: url) == port
            && url.user == nil && url.password == nil
    }

    private static func effectivePort(for url: URL) -> Int? {
        if let port = url.port { return port }
        switch url.scheme?.lowercased() {
        case "http": return 80
        case "https": return 443
        default: return nil
        }
    }
}
