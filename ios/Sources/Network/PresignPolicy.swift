import Foundation

/// Which hosts a presigned upload URL may point at. An entry starting with "." also allows
/// its subdomains, so ".r2.cloudflarestorage.com" covers every account's storage host.
nonisolated struct StorageHostPolicy: Sendable, Equatable {
    static let infoKey = "SPStorageHosts"

    let allowedHosts: [String]
    var allowsLocalHTTP = TransportSecurity.isDebugBuild

    static func fromInfoPlist(bundle: Bundle = .main) -> StorageHostPolicy {
        let text = bundle.object(forInfoDictionaryKey: infoKey) as? String ?? ""
        return StorageHostPolicy(allowedHosts: text.split(whereSeparator: \.isWhitespace).map { $0.lowercased() })
    }

    func allows(host: String) -> Bool {
        let host = host.lowercased()
        return allowedHosts.contains { entry in
            entry.hasPrefix(".") ? host.hasSuffix(entry) : host == entry
        }
    }
}

/// Checks a presign response before any bytes leave the phone: only the parts asked for, only
/// over TLS to the one storage host the server named, with only the headers S3 needs.
nonisolated enum PresignValidation {
    static let allowedHeaders: Set<String> = ["content-length", "content-md5", "content-type"]
    static let amazonHeaderPrefix = "x-amz-"
    static let expiryRange = 60...3600

    struct Validated: Sendable, Equatable {
        let parts: [PresignedPart]
        let expiresInSecs: Int
    }

    static func validate(_ response: PresignResponse, requested: [Int], policy: StorageHostPolicy) throws -> Validated {
        let numbers = response.parts.map(\.partNumber)
        guard Set(numbers).count == numbers.count, Set(numbers).isSubset(of: Set(requested)) else {
            throw APIError.malformedResponse
        }
        let parts = try response.parts.map { part in
            try checkURL(part.url, expectedHost: response.host, policy: policy)
            return PresignedPart(partNumber: part.partNumber, url: part.url, headers: allowedHeaders(of: part.headers))
        }
        return Validated(parts: parts, expiresInSecs: min(max(response.expiresInSecs, expiryRange.lowerBound), expiryRange.upperBound))
    }

    static func allowedHeaders(of headers: [String: String]) -> [String: String] {
        headers.filter { name, _ in
            let lowered = name.lowercased()
            return allowedHeaders.contains(lowered) || lowered.hasPrefix(amazonHeaderPrefix)
        }
    }

    private static func checkURL(_ url: URL, expectedHost: String?, policy: StorageHostPolicy) throws {
        guard TransportSecurity.isAllowed(url, allowsLocalHTTP: policy.allowsLocalHTTP), let host = url.host else {
            throw APIError.malformedResponse
        }
        let hostWithPort = url.port.map { "\(host):\($0)" } ?? host
        if let expectedHost, expectedHost.lowercased() != hostWithPort.lowercased() { throw APIError.malformedResponse }
        guard policy.allows(host: host) else { throw APIError.malformedResponse }
    }
}
