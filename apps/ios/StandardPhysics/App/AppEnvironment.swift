import Foundation

enum AppEnvironment {
    static var apiBaseURL: URL {
        configuredURL(named: "API_BASE_URL") ?? URL(string: "http://127.0.0.1:8787")!
    }

    static var workspaceBaseURL: URL {
        configuredURL(named: "WORKSPACE_BASE_URL") ?? URL(string: "http://127.0.0.1:3000")!
    }

    private static func configuredURL(named name: String) -> URL? {
        guard let value = ProcessInfo.processInfo.environment[name], !value.isEmpty else { return nil }
        return URL(string: value)
    }
}
