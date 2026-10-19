import Foundation

nonisolated struct UploadFileStatus: Sendable, Equatable, Identifiable {
    let id: UUID
    let scanID: String
    let fileName: String
    let state: UploadFileState
    let totalBytes: Int64
    let uploadedBytes: Int64

    var fractionCompleted: Double {
        guard totalBytes > 0 else { return 0 }
        return min(1, Double(uploadedBytes) / Double(totalBytes))
    }
}

nonisolated struct UploadSnapshot: Sendable, Equatable {
    var files: [UploadFileStatus]
    /// Set when the ledger could not be written to disk; resume after a kill may be incomplete.
    var persistenceError: String?

    var activeFiles: [UploadFileStatus] { files.filter { $0.state.isActive } }
    var isIdle: Bool { activeFiles.isEmpty }
    var totalBytes: Int64 { files.reduce(0) { $0 + $1.totalBytes } }
    var uploadedBytes: Int64 { files.reduce(0) { $0 + $1.uploadedBytes } }

    func files(forScan scanID: String) -> [UploadFileStatus] {
        files.filter { $0.scanID == scanID }
    }
}

nonisolated enum UploadError: Error, Equatable, LocalizedError {
    case emptyFile
    case fileFailed(name: String, message: String)

    var errorDescription: String? {
        switch self {
        case .emptyFile: "That file is empty, so there is nothing to upload."
        case .fileFailed(let name, let message): "\(name) could not be uploaded: \(message)"
        }
    }
}

nonisolated struct UploaderConfiguration: Sendable {
    var partSize = 8 * 1024 * 1024
    var maxConcurrentParts = 4
    var maxPartAttempts = 5
    var urlExpirySkew: TimeInterval = 120
    var retryBackoff = Backoff(base: .seconds(2), maximum: .seconds(60))
}

nonisolated struct PartKey: Hashable, Sendable {
    let fileID: UUID
    let number: Int

    var label: String { "\(fileID.uuidString)#\(number)" }

    init(fileID: UUID, number: Int) {
        self.fileID = fileID
        self.number = number
    }

    init?(label: String) {
        let pieces = label.split(separator: "#")
        guard pieces.count == 2, let id = UUID(uuidString: String(pieces[0])), let number = Int(pieces[1]) else { return nil }
        self.init(fileID: id, number: number)
    }
}
