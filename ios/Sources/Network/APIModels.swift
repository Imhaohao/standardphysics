import Foundation

// Wire types for sp-server (server/openapi.json). Field names match the spec exactly.

nonisolated struct EmptyResponse: Decodable, Sendable {}

// MARK: Auth

nonisolated struct ServerUser: Codable, Sendable, Equatable {
    let id: String
    let email: String?
}

nonisolated struct AuthSession: Codable, Sendable, Equatable {
    let token: String
    let expiresAt: Date
    let user: ServerUser

    enum CodingKeys: String, CodingKey {
        case token
        case expiresAt = "expires_at"
        case user
    }
}

nonisolated struct Credentials: Encodable, Sendable {
    let email: String
    let password: String
}

nonisolated struct AppleSignInRequest: Encodable, Sendable {
    let identityToken: String
    let nonce: String?

    enum CodingKeys: String, CodingKey {
        case identityToken = "identity_token"
        case nonce
    }
}

// MARK: Scans

nonisolated struct CreateScanRequest: Encodable, Sendable {
    let name: String?
    let siteName: String?

    enum CodingKeys: String, CodingKey {
        case name
        case siteName = "site_name"
    }
}

nonisolated struct ScanResponse: Codable, Sendable, Equatable {
    let id: String
    let name: String
    let siteName: String?
    let status: String
    let createdAt: Date
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, name, status
        case siteName = "site_name"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

// MARK: Uploads

nonisolated struct CreateUploadBody: Encodable, Sendable {
    let kind: String
    let filename: String
    let contentType: String
    let sizeBytes: Int64
    let partSize: Int?

    enum CodingKeys: String, CodingKey {
        case kind, filename
        case contentType = "content_type"
        case sizeBytes = "size_bytes"
        case partSize = "part_size"
    }
}

nonisolated struct UploadInfo: Codable, Sendable, Equatable {
    let id: String
    let scanID: String
    let kind: String
    let filename: String
    let contentType: String
    let sizeBytes: Int64
    let partSize: Int
    let partCount: Int
    let state: String
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, kind, filename, state
        case scanID = "scan_id"
        case contentType = "content_type"
        case sizeBytes = "size_bytes"
        case partSize = "part_size"
        case partCount = "part_count"
        case createdAt = "created_at"
    }
}

nonisolated struct PresignRequest: Encodable, Sendable {
    let partNumbers: [Int]

    enum CodingKeys: String, CodingKey {
        case partNumbers = "part_numbers"
    }
}

/// `headers` arrive as `[[name, value]]` and must be sent on the PUT unchanged.
nonisolated struct PresignedPart: Codable, Sendable, Equatable {
    let partNumber: Int
    let url: URL
    let headers: [String: String]

    enum CodingKeys: String, CodingKey {
        case partNumber = "part_number"
        case url, headers
    }

    init(partNumber: Int, url: URL, headers: [String: String] = [:]) {
        self.partNumber = partNumber
        self.url = url
        self.headers = headers
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        partNumber = try container.decode(Int.self, forKey: .partNumber)
        url = try container.decode(URL.self, forKey: .url)
        let pairs = try container.decode([[String]].self, forKey: .headers)
        headers = Dictionary(pairs.compactMap { $0.count == 2 ? ($0[0], $0[1]) : nil }, uniquingKeysWith: { $1 })
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(partNumber, forKey: .partNumber)
        try container.encode(url, forKey: .url)
        try container.encode(headers.sorted { $0.key < $1.key }.map { [$0.key, $0.value] }, forKey: .headers)
    }
}

nonisolated struct PresignResponse: Codable, Sendable, Equatable {
    let parts: [PresignedPart]
    let expiresInSecs: Int

    enum CodingKeys: String, CodingKey {
        case parts
        case expiresInSecs = "expires_in_secs"
    }
}

nonisolated struct UploadedPart: Codable, Sendable, Equatable {
    let partNumber: Int
    let etag: String
    let sizeBytes: Int64

    enum CodingKeys: String, CodingKey {
        case etag
        case partNumber = "part_number"
        case sizeBytes = "size_bytes"
    }
}

nonisolated struct UploadStatusResponse: Codable, Sendable, Equatable {
    let upload: UploadInfo
    let uploadedParts: [UploadedPart]

    enum CodingKeys: String, CodingKey {
        case upload
        case uploadedParts = "uploaded_parts"
    }
}

nonisolated struct CompleteUploadRequest: Encodable, Sendable {
    let sha256: String
}

nonisolated struct Artifact: Codable, Sendable, Equatable {
    let id: String
    let scanID: String
    let uploadID: String
    let kind: String
    let filename: String
    let contentType: String
    let sizeBytes: Int64
    let sha256: String
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, kind, filename, sha256
        case scanID = "scan_id"
        case uploadID = "upload_id"
        case contentType = "content_type"
        case sizeBytes = "size_bytes"
        case createdAt = "created_at"
    }
}

// MARK: Findings and report

nonisolated enum JSONValue: Codable, Sendable, Equatable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null }
        else if let value = try? container.decode(Bool.self) { self = .bool(value) }
        else if let value = try? container.decode(Double.self) { self = .number(value) }
        else if let value = try? container.decode(String.self) { self = .string(value) }
        else if let value = try? container.decode([JSONValue].self) { self = .array(value) }
        else { self = .object(try container.decode([String: JSONValue].self)) }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null: try container.encodeNil()
        case .bool(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .string(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        }
    }

    init(jsonData: Data) throws {
        self = try JSONDecoder().decode(JSONValue.self, from: jsonData)
    }
}

nonisolated struct ServerMeasured: Codable, Sendable, Equatable {
    let text: String
    let value: Double?
    let lo: Double?
    let hi: Double?
    let unit: String
}

nonisolated struct Point3: Codable, Sendable, Equatable {
    let x: Double
    let y: Double
    let z: Double
}

/// A finding exactly as sp-server sends it. The shared `Finding` is a subset; see `asFinding`.
nonisolated struct ServerFinding: Codable, Sendable, Equatable, Identifiable {
    let ruleID: String
    let jurisdiction: String
    let section: String
    let title: String
    let subjectID: String
    let roomID: String?
    let status: FindingStatus
    let severity: String
    let measured: ServerMeasured?
    let required: String
    let message: String
    let evidence: String
    let location: Point3?
    let counterpart: String?

    var id: String { "\(ruleID)#\(subjectID)" }

    enum CodingKeys: String, CodingKey {
        case ruleID = "rule_id"
        case jurisdiction, section, title
        case subjectID = "subject_id"
        case roomID = "room_id"
        case status, severity, measured, required, message, evidence, location, counterpart
    }

    /// Nil for jurisdictions the app has no type for (e.g. SYSTEM label findings), so callers
    /// that need every server finding should read the report's `findings` directly.
    var asFinding: Finding? {
        guard let jurisdiction = Jurisdiction(rawValue: jurisdiction) else { return nil }
        return Finding(
            ruleID: ruleID, jurisdiction: jurisdiction, section: section, subjectID: subjectID,
            status: status, measured: measured?.asMeasuredValue, required: required, message: message
        )
    }
}

nonisolated extension ServerMeasured {
    /// The shared type holds one number; a range reports its lower bound.
    var asMeasuredValue: MeasuredValue? {
        guard let number = value ?? lo ?? hi else { return nil }
        return MeasuredValue(value: number, unit: unit)
    }
}

nonisolated struct StatusCounts: Codable, Sendable, Equatable {
    let pass: Int
    let fail: Int
    let needsInfo: Int
    let notApplicable: Int

    enum CodingKeys: String, CodingKey {
        case pass, fail
        case needsInfo = "needs_info"
        case notApplicable = "not_applicable"
    }
}

nonisolated struct FindingsSummary: Codable, Sendable, Equatable {
    let total: StatusCounts
    let byJurisdiction: [String: StatusCounts]
    let governing: [Governing]?
    let governingCounts: StatusCounts?

    enum CodingKeys: String, CodingKey {
        case total, governing
        case byJurisdiction = "by_jurisdiction"
        case governingCounts = "governing_counts"
    }
}

/// Where ADA and California disagree about a subject, the stricter result governs.
nonisolated struct Governing: Codable, Sendable, Equatable {
    let subjectID: String
    let status: FindingStatus
    let governingRuleID: String
    let governingJurisdiction: String
    let ruleIDs: [String]
    let message: String

    enum CodingKeys: String, CodingKey {
        case status, message
        case subjectID = "subject_id"
        case governingRuleID = "governing_rule_id"
        case governingJurisdiction = "governing_jurisdiction"
        case ruleIDs = "rule_ids"
    }
}

nonisolated struct StageTimings: Codable, Sendable, Equatable {
    let loadMs: Int
    let labellingMs: Int
    let evaluationMs: Int
    let persistMs: Int
    let totalMs: Int

    enum CodingKeys: String, CodingKey {
        case loadMs = "load_ms"
        case labellingMs = "labelling_ms"
        case evaluationMs = "evaluation_ms"
        case persistMs = "persist_ms"
        case totalMs = "total_ms"
    }
}

nonisolated struct Report: Codable, Sendable, Equatable {
    let scanID: String
    let assessmentID: String
    let createdAt: Date
    let summary: FindingsSummary
    let findings: [ServerFinding]
    let timings: StageTimings
    let labelledByVision: Int
    let unlabelledObjects: Int

    enum CodingKeys: String, CodingKey {
        case summary, findings, timings
        case scanID = "scan_id"
        case assessmentID = "assessment_id"
        case createdAt = "created_at"
        case labelledByVision = "labelled_by_vision"
        case unlabelledObjects = "unlabelled_objects"
    }
}

nonisolated struct APIErrorBody: Decodable, Sendable {
    let error: String?
    let message: String?
}

// MARK: Live channel

/// Sent per room as it is captured, and again when the room is finished (`isFinal`).
/// The server merges observations by id and replaces `capturedRoom`.
nonisolated struct RoomUpdate: Codable, Sendable, Equatable {
    let roomID: String
    let isFinal: Bool
    let seq: Int?
    let capturedRoom: JSONValue?
    let observations: [JSONValue]

    static let wireType = "room"

    enum CodingKeys: String, CodingKey {
        case type
        case roomID = "room_id"
        case isFinal = "final"
        case seq
        case capturedRoom = "captured_room"
        case observations
    }

    init(roomID: String, isFinal: Bool, seq: Int? = nil, capturedRoom: JSONValue? = nil, observations: [JSONValue] = []) {
        self.roomID = roomID
        self.isFinal = isFinal
        self.seq = seq
        self.capturedRoom = capturedRoom
        self.observations = observations
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        roomID = try container.decode(String.self, forKey: .roomID)
        isFinal = try container.decodeIfPresent(Bool.self, forKey: .isFinal) ?? false
        seq = try container.decodeIfPresent(Int.self, forKey: .seq)
        capturedRoom = try container.decodeIfPresent(JSONValue.self, forKey: .capturedRoom)
        observations = try container.decodeIfPresent([JSONValue].self, forKey: .observations) ?? []
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(Self.wireType, forKey: .type)
        try container.encode(roomID, forKey: .roomID)
        try container.encode(isFinal, forKey: .isFinal)
        try container.encodeIfPresent(seq, forKey: .seq)
        try container.encodeIfPresent(capturedRoom, forKey: .capturedRoom)
        try container.encode(observations, forKey: .observations)
    }
}

nonisolated struct RoomFindings: Sendable, Equatable {
    let roomID: String
    let seq: Int?
    let isFinal: Bool
    let findings: [ServerFinding]
    let summary: FindingsSummary
    let elapsedMs: Int
}

nonisolated struct LiveSnapshot: Sendable, Equatable {
    let scanID: String
    let rooms: [String]
    let findings: [ServerFinding]
    let summary: FindingsSummary
}

nonisolated enum LiveMessage: Sendable, Equatable {
    /// Full state of the scan. Sent on every (re)connect; replace what you hold.
    case hello(LiveSnapshot)
    case findings(RoomFindings)
    case report(Report)
    case serverError(message: String)
    /// Geometry of one room as the server holds it, for live drawing.
    case room(JSONValue)
    case scene(JSONValue)
    case pong
    case unknown(type: String)
}

extension LiveMessage: Decodable {
    private enum CodingKeys: String, CodingKey {
        case type, message, report, findings, summary, rooms, seq, final, room, scene
        case scanID = "scan_id"
        case roomID = "room_id"
        case elapsedMs = "elapsed_ms"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        switch try container.decode(String.self, forKey: .type) {
        case "hello": self = .hello(try Self.snapshot(from: container))
        case "findings": self = .findings(try Self.roomFindings(from: container))
        case "report": self = .report(try container.decode(Report.self, forKey: .report))
        case "error": self = .serverError(message: try container.decodeIfPresent(String.self, forKey: .message) ?? "")
        case "room": self = .room(try container.decode(JSONValue.self, forKey: .room))
        case "scene": self = .scene(try container.decode(JSONValue.self, forKey: .scene))
        case "pong": self = .pong
        case let other: self = .unknown(type: other)
        }
    }

    private static func snapshot(from container: KeyedDecodingContainer<CodingKeys>) throws -> LiveSnapshot {
        LiveSnapshot(
            scanID: try container.decode(String.self, forKey: .scanID),
            rooms: try container.decode([String].self, forKey: .rooms),
            findings: try container.decode([ServerFinding].self, forKey: .findings),
            summary: try container.decode(FindingsSummary.self, forKey: .summary)
        )
    }

    private static func roomFindings(from container: KeyedDecodingContainer<CodingKeys>) throws -> RoomFindings {
        RoomFindings(
            roomID: try container.decode(String.self, forKey: .roomID),
            seq: try container.decodeIfPresent(Int.self, forKey: .seq),
            isFinal: try container.decode(Bool.self, forKey: .final),
            findings: try container.decode([ServerFinding].self, forKey: .findings),
            summary: try container.decode(FindingsSummary.self, forKey: .summary),
            elapsedMs: try container.decode(Int.self, forKey: .elapsedMs)
        )
    }
}

nonisolated enum WireCoding {
    static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }

    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let text = try decoder.singleValueContainer().decode(String.self)
            guard let date = parseDate(text) else {
                throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Bad date \(text)"))
            }
            return date
        }
        return decoder
    }

    private static func parseDate(_ text: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: text) { return date }
        return ISO8601DateFormatter().date(from: text)
    }
}
