import Foundation

enum AppEnvironment {
    static var apiBaseURL: URL? {
        configuredURL(named: "API_BASE_URL")
    }

    static var workspaceBaseURL: URL? {
        configuredURL(named: "WORKSPACE_BASE_URL")
    }

    private static func configuredURL(named name: String) -> URL? {
        let defaults = UserDefaults.standard
        if let value = ProcessInfo.processInfo.environment[name], let url = try? ServiceAddress.parse(value) {
            defaults.set(url.absoluteString, forKey: name)
            return url
        }
        let value = defaults.string(forKey: name) ?? Bundle.main.object(forInfoDictionaryKey: name) as? String
        return value.flatMap { try? ServiceAddress.parse($0) }
    }

    static func save(api: String, workspace: String) throws {
        let apiURL = try ServiceAddress.parse(api)
        let webURL = workspace.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? nil : try ServiceAddress.parse(workspace)
        UserDefaults.standard.set(apiURL.absoluteString, forKey: "API_BASE_URL")
        UserDefaults.standard.set(webURL?.absoluteString, forKey: "WORKSPACE_BASE_URL")
    }
}

enum ServiceAddress {
    static func parse(_ value: String) throws -> URL {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let parts = URLComponents(string: trimmed),
              let scheme = parts.scheme?.lowercased(), ["https", "http"].contains(scheme),
              let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil,
              parts.query == nil, parts.fragment == nil,
              parts.port.map({ (1...65535).contains($0) }) ?? true,
              let url = parts.url else { throw AddressError.invalid }
        guard scheme == "https" || isLocalHost(host) else { throw AddressError.requiresHTTPS }
#if !targetEnvironment(simulator)
        guard !isLoopback(host) else { throw AddressError.phoneLoopback }
#endif
        return url
    }

    static func isLoopback(_ host: String) -> Bool {
        let host = host.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        return host == "localhost" || host == "::1" || ipv4Octets(host)?.first == 127
    }

    static func isLocalHost(_ host: String) -> Bool {
        let host = host.lowercased()
        if isLoopback(host) || host.hasSuffix(".local") { return true }
        guard let parts = ipv4Octets(host) else { return false }
        return parts[0] == 10 || (parts[0] == 192 && parts[1] == 168)
            || (parts[0] == 172 && (16...31).contains(parts[1]))
            || (parts[0] == 169 && parts[1] == 254)
    }

    private static func ipv4Octets(_ host: String) -> [Int]? {
        let parts = host.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 4, parts.allSatisfy({ !$0.isEmpty && $0.allSatisfy { $0.isASCII && $0.isNumber } }) else { return nil }
        let octets = parts.compactMap { Int($0) }
        return octets.count == 4 && octets.allSatisfy({ (0...255).contains($0) }) ? octets : nil
    }

    enum AddressError: LocalizedError {
        case invalid, requiresHTTPS, phoneLoopback
        var errorDescription: String? {
            switch self {
            case .invalid: "Enter a full address, such as https://your-workspace.example."
            case .requiresHTTPS: "Use an https address for your hosted workspace."
            case .phoneLoopback: "Enter your Mac’s network address so this phone can reach it."
            }
        }
    }
}
