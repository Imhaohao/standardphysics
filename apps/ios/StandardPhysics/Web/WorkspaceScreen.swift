import SwiftUI
import WebKit

struct WorkspaceScreen: View {
    @ObservedObject var appModel: AppModel
    let scanID: String

    var body: some View {
        NavigationStack {
            WorkspaceWebView(
                url: AppEnvironment.workspaceBaseURL
                    .appendingPathComponent("scans")
                    .appendingPathComponent(scanID),
                allowedHosts: [AppEnvironment.workspaceBaseURL.host].compactMap { $0 },
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
    let allowedHosts: Set<String>
    let onScanRequested: () -> Void

    init(url: URL, allowedHosts: [String], onScanRequested: @escaping () -> Void) {
        self.url = url
        self.allowedHosts = Set(allowedHosts)
        self.onScanRequested = onScanRequested
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(allowedHosts: allowedHosts, onScanRequested: onScanRequested)
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
        private let allowedHosts: Set<String>
        private let onScanRequested: () -> Void

        init(allowedHosts: Set<String>, onScanRequested: @escaping () -> Void) {
            self.allowedHosts = allowedHosts
            self.onScanRequested = onScanRequested
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction
        ) async -> WKNavigationActionPolicy {
            guard let target = navigationAction.request.url else { return .cancel }
            if target.scheme == "about" || target.host.map(allowedHosts.contains) == true {
                return .allow
            } else {
                return .cancel
            }
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "nativeCapture",
                  let action = message.body as? String,
                  action == "scanShop" else { return }
            DispatchQueue.main.async { self.onScanRequested() }
        }
    }
}
