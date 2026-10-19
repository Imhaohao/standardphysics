import Foundation

/// Where the uploader keeps files. Everything lives under one root in Application Support so
/// paths can be rebuilt after the app container moves; only names are persisted.
nonisolated struct UploadStorage: Sendable {
    let root: URL

    static func applicationSupport() throws -> UploadStorage {
        let base = try FileManager.default.url(
            for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true
        )
        return UploadStorage(root: base.appendingPathComponent("Uploads", isDirectory: true))
    }

    var ledgerURL: URL { root.appendingPathComponent("upload-ledger.json") }

    func stagedFileURL(for fileID: UUID) -> URL {
        root.appendingPathComponent("staged", isDirectory: true).appendingPathComponent(fileID.uuidString)
    }

    func partFileURL(for fileID: UUID, partNumber: Int) -> URL {
        partsDirectory(for: fileID).appendingPathComponent("part-\(partNumber)")
    }

    func ensureDirectories() throws {
        let attributes: [FileAttributeKey: Any] = [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]
        for directory in [root, stagedFileURL(for: UUID()).deletingLastPathComponent(), partsRoot] {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: attributes)
        }
    }

    @concurrent
    func stage(_ source: URL, as fileID: UUID) async throws {
        try ensureDirectories()
        let destination = stagedFileURL(for: fileID)
        try? FileManager.default.removeItem(at: destination)
        try FileManager.default.copyItem(at: source, to: destination)
    }

    func removeFiles(for fileID: UUID) {
        try? FileManager.default.removeItem(at: stagedFileURL(for: fileID))
        try? FileManager.default.removeItem(at: partsDirectory(for: fileID))
    }

    func removePartFile(for fileID: UUID, partNumber: Int) {
        try? FileManager.default.removeItem(at: partFileURL(for: fileID, partNumber: partNumber))
    }

    private var partsRoot: URL { root.appendingPathComponent("parts", isDirectory: true) }

    private func partsDirectory(for fileID: UUID) -> URL {
        partsRoot.appendingPathComponent(fileID.uuidString, isDirectory: true)
    }
}
