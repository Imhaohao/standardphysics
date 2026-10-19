import Foundation

nonisolated struct UploadPart: Codable, Sendable, Equatable {
    let number: Int
    var url: URL?
    var headers: [String: String] = [:]
    var expiresAt: Date = .distantPast
    var etag: String?
    var failureCount = 0

    var isComplete: Bool { etag != nil }

    func needsFreshURL(at date: Date, skew: TimeInterval) -> Bool {
        url == nil || expiresAt.timeIntervalSince(date) <= skew
    }
}

nonisolated struct MultipartSession: Codable, Sendable, Equatable {
    let uploadID: String
    let partSize: Int
    var parts: [UploadPart]
}

nonisolated enum UploadFileState: Codable, Sendable, Equatable {
    case queued
    case uploading
    case completing
    case completed
    case failed(message: String)

    var failureMessage: String? {
        guard case .failed(let message) = self else { return nil }
        return message
    }

    var isActive: Bool {
        switch self {
        case .queued, .uploading, .completing: true
        case .completed, .failed: false
        }
    }
}

nonisolated struct UploadRecord: Codable, Sendable, Equatable, Identifiable {
    let id: UUID
    let scanID: String
    let fileName: String
    let kind: String
    let contentType: String
    let sizeBytes: Int64
    let sha256: String
    let enqueuedAt: Date
    var state: UploadFileState
    var multipart: MultipartSession?
    /// How many times the server forgot the multipart upload. Each restart needs a new
    /// idempotency key, or the server would replay the upload it already dropped.
    var restarts: Int?

    var createKey: String {
        let count = restarts ?? 0
        return count == 0 ? id.uuidString : "\(id.uuidString)-restart-\(count)"
    }
}

/// Durable record of every upload. The whole file is rewritten atomically after each change,
/// so a kill mid-write leaves either the old or the new ledger, never a torn one.
actor UploadLedger {
    private let fileURL: URL
    private var loaded: [UUID: UploadRecord]?

    init(fileURL: URL) {
        self.fileURL = fileURL
    }

    func all() -> [UploadRecord] {
        currentRecords().values.sorted { $0.enqueuedAt < $1.enqueuedAt }
    }

    func record(_ id: UUID) -> UploadRecord? {
        currentRecords()[id]
    }

    func insert(_ record: UploadRecord) throws {
        var records = currentRecords()
        records[record.id] = record
        try commit(records)
    }

    @discardableResult
    func update(_ id: UUID, _ change: @Sendable (inout UploadRecord) -> Void) throws -> UploadRecord? {
        var records = currentRecords()
        guard var record = records[id] else { return nil }
        change(&record)
        records[id] = record
        try commit(records)
        return record
    }

    func remove(_ ids: [UUID]) throws {
        var records = currentRecords()
        ids.forEach { records[$0] = nil }
        try commit(records)
    }

    private func currentRecords() -> [UUID: UploadRecord] {
        if let loaded { return loaded }
        let records = readFromDisk()
        loaded = records
        return records
    }

    private func commit(_ records: [UUID: UploadRecord]) throws {
        let data = try WireCoding.encoder().encode(records.values.sorted { $0.enqueuedAt < $1.enqueuedAt })
        try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: fileURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        loaded = records
    }

    private func readFromDisk() -> [UUID: UploadRecord] {
        guard let data = try? Data(contentsOf: fileURL) else { return [:] }
        guard let list = try? WireCoding.decoder().decode([UploadRecord].self, from: data) else {
            quarantineUnreadableLedger()
            return [:]
        }
        return Dictionary(uniqueKeysWithValues: list.map { ($0.id, $0) })
    }

    private func quarantineUnreadableLedger() {
        let aside = fileURL.appendingPathExtension("unreadable-\(Int(Date().timeIntervalSince1970))")
        try? FileManager.default.moveItem(at: fileURL, to: aside)
    }
}
