import Foundation

/// A presigned URL is a bearer credential for one part, so it lives only in memory. After a
/// relaunch every unfinished part asks the server for a fresh one.
nonisolated struct UploadPart: Codable, Sendable, Equatable {
    let number: Int
    var url: URL?
    var headers: [String: String] = [:]
    var expiresAt: Date = .distantPast
    var etag: String?
    var failureCount = 0

    enum CodingKeys: String, CodingKey {
        case number, etag, failureCount
    }

    init(number: Int, url: URL? = nil, headers: [String: String] = [:], expiresAt: Date = .distantPast, etag: String? = nil, failureCount: Int = 0) {
        self.number = number
        self.url = url
        self.headers = headers
        self.expiresAt = expiresAt
        self.etag = etag
        self.failureCount = failureCount
    }

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

/// Why an upload stopped for good. Only the code is stored; the words come from the app, so
/// nothing a server or URLSession said is written to disk or shown verbatim.
nonisolated enum UploadFailure: String, Codable, Sendable {
    case storageRejected
    case network
    case signedOut
    case notAllowed
    case serverRejected
    case invalidServerResponse
    case fileUnreadable

    init(_ error: APIError) {
        switch error {
        case .unauthorized: self = .signedOut
        case .forbidden: self = .notAllowed
        case .malformedResponse, .responseTooLarge: self = .invalidServerResponse
        case .offline, .timedOut, .transport: self = .network
        default: self = .serverRejected
        }
    }

    init(partStatusCode: Int?) {
        self = partStatusCode == nil ? .network : .storageRejected
    }

    var userMessage: String {
        switch self {
        case .storageRejected: "Our storage kept refusing part of this file. Try the upload again later."
        case .network: "The connection kept dropping while this file uploaded. Try again on a steadier network."
        case .signedOut: "Your session ended. Sign in again to finish uploading."
        case .notAllowed: "Your account can't upload to this scan."
        case .serverRejected: "The server didn't accept this file. Try again later."
        case .invalidServerResponse: "The server answered in a way the app didn't expect, so the upload stopped. Update the app and try again."
        case .fileUnreadable: "This phone couldn't read the saved file, so it can't be uploaded."
        }
    }
}

nonisolated enum UploadFileState: Codable, Sendable, Equatable {
    case queued
    case uploading
    case completing
    case completed
    case failed(UploadFailure)

    var failure: UploadFailure? {
        guard case .failed(let failure) = self else { return nil }
        return failure
    }

    var failureMessage: String? { failure?.userMessage }

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
        try ProtectedDirectory.create(fileURL.deletingLastPathComponent(), excludingFromBackup: true)
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
