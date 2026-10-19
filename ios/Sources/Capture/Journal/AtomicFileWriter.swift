import Foundation

nonisolated protocol AtomicFileWriting: Sendable {
    func write(_ data: Data, to url: URL, protection: FileProtectionType) throws
}

extension AtomicFileWriting {
    /// Readable after the first unlock, so background work can still reach the file while the
    /// phone is locked again.
    nonisolated func write(_ data: Data, to url: URL) throws {
        try write(data, to: url, protection: .completeUntilFirstUserAuthentication)
    }
}

/// Folders that hold scan data: encrypted until first unlock and never copied into iCloud or
/// computer backups, since the server keeps the finished results.
nonisolated enum ProtectedDirectory {
    static func create(_ url: URL, excludingFromBackup: Bool = false) throws {
        try FileManager.default.createDirectory(
            at: url, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]
        )
        guard excludingFromBackup else { return }
        var excluded = url
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try excluded.setResourceValues(values)
    }
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

    func write(_ data: Data, to url: URL, protection: FileProtectionType) throws {
        let temporary = Self.temporaryURL(for: url)
        do {
            try data.write(to: temporary, options: Self.writingOptions(for: protection))
            try Self.flush(temporary)
            try Self.rename(temporary, to: url)
        } catch {
            try? FileManager.default.removeItem(at: temporary)
            throw error
        }
    }

    static func writingOptions(for protection: FileProtectionType) -> Data.WritingOptions {
        switch protection {
        case .complete: .completeFileProtection
        case .completeUnlessOpen: .completeFileProtectionUnlessOpen
        case .none: .noFileProtection
        default: .completeFileProtectionUntilFirstUserAuthentication
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
