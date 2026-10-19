import CryptoKit
import Foundation
import Security

nonisolated enum AppleNonceError: Error, Equatable {
    case randomBytesUnavailable(OSStatus)
}

/// Apple puts `hashed` into the identity token; the server receives `raw` and hashes it again,
/// so a token lifted from another sign-in cannot be replayed without the raw value.
nonisolated struct AppleNonce: Sendable, Equatable {
    static let byteCount = 32

    let raw: String
    var hashed: String { Self.sha256Hex(raw) }

    init(raw: String) {
        self.raw = raw
    }

    static func make() throws -> AppleNonce {
        var bytes = [UInt8](repeating: 0, count: byteCount)
        let status = SecRandomCopyBytes(kSecRandomDefault, byteCount, &bytes)
        guard status == errSecSuccess else { throw AppleNonceError.randomBytesUnavailable(status) }
        return AppleNonce(raw: hex(bytes))
    }

    static func sha256Hex(_ text: String) -> String {
        hex(Array(SHA256.hash(data: Data(text.utf8))))
    }

    private static func hex(_ bytes: [UInt8]) -> String {
        bytes.map { String(format: "%02x", $0) }.joined()
    }
}
