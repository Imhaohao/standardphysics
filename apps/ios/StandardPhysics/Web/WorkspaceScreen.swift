import SwiftUI
import WebKit

struct WorkspaceScreen: View {
    @ObservedObject var appModel: AppModel
    let scanID: String

    var body: some View {
        let workspaceURL = AppEnvironment.workspaceBaseURL
        NavigationStack {
            WorkspaceWebView(
                url: workspaceURL
                    .appendingPathComponent("scans")
                    .appendingPathComponent(scanID),
                allowedOrigin: WebOrigin(url: workspaceURL)!,
                onScanRequested: { appModel.screen = .capture }
            )
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
    let onScanRequested: () -> Void

    init(url: URL, allowedOrigin: WebOrigin, onScanRequested: @escaping () -> Void) {
        self.url = url
        self.allowedOrigin = allowedOrigin
        self.onScanRequested = onScanRequested
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(allowedOrigin: allowedOrigin, onScanRequested: onScanRequested)
    }

    func makeUIView(context: Context) -> WKWebView {
        let contentController = WKUserContentController()
        contentController.add(context.coordinator, name: "nativeCapture")
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.userContentController = contentController
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        guard webView.url != url else { return }
        webView.load(URLRequest(url: url))
    }

    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "nativeCapture")
        webView.navigationDelegate = nil
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        private let allowedOrigin: WebOrigin
        private let onScanRequested: () -> Void

        init(allowedOrigin: WebOrigin, onScanRequested: @escaping () -> Void) {
            self.allowedOrigin = allowedOrigin
            self.onScanRequested = onScanRequested
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction
        ) async -> WKNavigationActionPolicy {
            guard let target = navigationAction.request.url else { return .cancel }
            if target.absoluteString == "about:blank" || allowedOrigin.contains(target) {
                return .allow
            } else {
                return .cancel
            }
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "nativeCapture",
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
