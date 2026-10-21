import Foundation

/// Links into the web app. Without `SPWebBaseURL` in Info.plist the app offers no links.
nonisolated enum WebLinks {
    static let baseURLInfoKey = "SPWebBaseURL"

    static func baseURL(in bundle: Bundle = .main) -> URL? {
        baseURL(from: bundle.object(forInfoDictionaryKey: baseURLInfoKey) as? String)
    }

    /// Empty means not configured; anything but https (or the debug local server) is refused.
    static func baseURL(from text: String?) -> URL? {
        guard let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty,
              let url = URL(string: trimmed), TransportSecurity.isAllowed(url) else { return nil }
        return url
    }

    /// `base/r/token`. A token with anything but URL-safe characters is refused rather than
    /// pasted into a link.
    static func sharedReportURL(base: URL, token: String) -> URL? {
        guard !token.isEmpty, token.unicodeScalars.allSatisfy(isTokenCharacter) else { return nil }
        var text = base.absoluteString
        while text.hasSuffix("/") { text.removeLast() }
        return URL(string: "\(text)/r/\(token)")
    }

    private static func isTokenCharacter(_ scalar: Unicode.Scalar) -> Bool {
        scalar.isASCII && (CharacterSet.alphanumerics.contains(scalar) || scalar == "-" || scalar == "_")
    }
}
