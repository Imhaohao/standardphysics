import Foundation

nonisolated protocol AtomicFileWriting: Sendable {
    func write(_ data: Data, to url: URL) throws
}

/// Writes to a sibling temp file, flushes it to disk, then renames over the destination.
/// `rename(2)` is atomic on APFS, so a reader sees either the old file or the new one.
nonisolated struct AtomicFileWriter: AtomicFileWriting {
    static let temporarySuffix = ".tmp"

    static func temporaryURL(for url: URL) -> URL {
        url.deletingLastPathComponent()
            .appending(path: ".\(url.lastPathComponent).\(UUID().uuidString)\(temporarySuffix)")
    }

    static func isTemporaryFile(_ url: URL) -> Bool {
        url.lastPathComponent.hasPrefix(".") && url.lastPathComponent.hasSuffix(temporarySuffix)
    }

    func write(_ data: Data, to url: URL) throws {
        let temporary = Self.temporaryURL(for: url)
        do {
            try data.write(to: temporary)
            try Self.flush(temporary)
            try Self.rename(temporary, to: url)
        } catch {
            try? FileManager.default.removeItem(at: temporary)
            throw error
        }
    }

    private static func flush(_ url: URL) throws {
        let handle = try FileHandle(forWritingTo: url)
        defer { try? handle.close() }
        try handle.synchronize()
    }

    private static func rename(_ source: URL, to destination: URL) throws {
        guard Darwin.rename(source.path, destination.path) == 0 else {
            throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
        }
    }
}
