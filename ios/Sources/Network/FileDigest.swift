import CryptoKit
import Foundation

nonisolated enum FileDigest {
    static let readChunkSize = 1 << 20

    /// Streams the file so memory stays flat for large meshes.
    @concurrent
    static func sha256Hex(of url: URL) async throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var hasher = SHA256()
        while let chunk = try handle.read(upToCount: readChunkSize), !chunk.isEmpty {
            hasher.update(data: chunk)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}
