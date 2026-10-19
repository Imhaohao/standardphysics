import Foundation

nonisolated struct AuthSession: Codable, Sendable, Equatable {
    let accessToken: String
    let expiresAt: Date?

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case expiresAt = "expires_at"
    }
}

nonisolated struct SignInRequest: Encodable, Sendable {
    let email: String
    let password: String
}

nonisolated struct AppleSignInRequest: Encodable, Sendable {
    let identityToken: String
    let fullName: String?

    enum CodingKeys: String, CodingKey {
        case identityToken = "identity_token"
        case fullName = "full_name"
    }
}

nonisolated struct CreateScanRequest: Encodable, Sendable {
    let clientID: String
    let name: String

    enum CodingKeys: String, CodingKey {
        case clientID = "client_id"
        case name
    }
}

nonisolated struct ScanResponse: Codable, Sendable, Equatable {
    let id: String
    let clientID: String
    let name: String
    let status: String

    enum CodingKeys: String, CodingKey {
        case id
        case clientID = "client_id"
        case name, status
    }
}

nonisolated struct RequestUploadBody: Encodable, Sendable {
    let fileName: String
    let contentType: String
    let sizeBytes: Int64
    let partSize: Int

    enum CodingKeys: String, CodingKey {
        case fileName = "file_name"
        case contentType = "content_type"
        case sizeBytes = "size_bytes"
        case partSize = "part_size"
    }
}

nonisolated struct PresignedPart: Codable, Sendable, Equatable {
    let partNumber: Int
    let url: URL
    let expiresAt: Date

    enum CodingKeys: String, CodingKey {
        case partNumber = "part_number"
        case url
        case expiresAt = "expires_at"
    }
}

nonisolated struct MultipartUploadGrant: Codable, Sendable, Equatable {
    let uploadID: String
    let partSize: Int
    let parts: [PresignedPart]

    enum CodingKeys: String, CodingKey {
        case uploadID = "upload_id"
        case partSize = "part_size"
        case parts
    }
}

nonisolated struct RefreshPartsRequest: Encodable, Sendable {
    let partNumbers: [Int]

    enum CodingKeys: String, CodingKey {
        case partNumbers = "part_numbers"
    }
}

nonisolated struct PartsResponse: Codable, Sendable, Equatable {
    let parts: [PresignedPart]
}

nonisolated struct CompletedPart: Codable, Sendable, Equatable {
    let partNumber: Int
    let etag: String

    enum CodingKeys: String, CodingKey {
        case partNumber = "part_number"
        case etag
    }
}

nonisolated struct CompleteUploadRequest: Encodable, Sendable {
    let parts: [CompletedPart]
}

nonisolated struct CompleteUploadResponse: Codable, Sendable, Equatable {
    let fileKey: String

    enum CodingKeys: String, CodingKey {
        case fileKey = "file_key"
    }
}

nonisolated struct CompleteScanResponse: Codable, Sendable, Equatable {
    let jobID: String
    let status: String

    enum CodingKeys: String, CodingKey {
        case jobID = "job_id"
        case status
    }
}

nonisolated struct FindingsResponse: Codable, Sendable, Equatable {
    let findings: [Finding]
    let lastEventID: Int?
    let status: String

    enum CodingKeys: String, CodingKey {
        case findings
        case lastEventID = "last_event_id"
        case status
    }
}

nonisolated struct APIErrorBody: Decodable, Sendable {
    let message: String?
}

// MARK: - Live channel wire format

nonisolated struct RoomFinishedEvent: Codable, Sendable, Equatable {
    let clientEventID: UUID
    let roomIndex: Int
    let name: String
    let fileKey: String?

    enum CodingKeys: String, CodingKey {
        case type
        case clientEventID = "client_event_id"
        case roomIndex = "room_index"
        case name
        case fileKey = "file_key"
    }

    static let wireType = "room_finished"

    init(clientEventID: UUID = UUID(), roomIndex: Int, name: String, fileKey: String?) {
        self.clientEventID = clientEventID
        self.roomIndex = roomIndex
        self.name = name
        self.fileKey = fileKey
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        clientEventID = try container.decode(UUID.self, forKey: .clientEventID)
        roomIndex = try container.decode(Int.self, forKey: .roomIndex)
        name = try container.decode(String.self, forKey: .name)
        fileKey = try container.decodeIfPresent(String.self, forKey: .fileKey)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(Self.wireType, forKey: .type)
        try container.encode(clientEventID, forKey: .clientEventID)
        try container.encode(roomIndex, forKey: .roomIndex)
        try container.encode(name, forKey: .name)
        try container.encodeIfPresent(fileKey, forKey: .fileKey)
    }
}

nonisolated struct ScanProgress: Codable, Sendable, Equatable {
    let stage: String
    let fraction: Double
    let message: String?
}

nonisolated enum LiveMessageKind: Sendable, Equatable {
    case finding(Finding)
    case progress(ScanProgress)
    case roomAcknowledged(clientEventID: UUID)
    case scanCompleted
    case serverError(message: String)
    case heartbeat
    case unknown(type: String)
}

nonisolated struct LiveMessage: Sendable, Equatable {
    let eventID: Int?
    let kind: LiveMessageKind
}

extension LiveMessage: Decodable {
    private enum CodingKeys: String, CodingKey {
        case type
        case eventID = "event_id"
        case finding, message
        case clientEventID = "client_event_id"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let type = try container.decode(String.self, forKey: .type)
        eventID = try container.decodeIfPresent(Int.self, forKey: .eventID)
        kind = try Self.decodeKind(type: type, container: container, decoder: decoder)
    }

    private static func decodeKind(
        type: String, container: KeyedDecodingContainer<CodingKeys>, decoder: Decoder
    ) throws -> LiveMessageKind {
        switch type {
        case "finding": return .finding(try container.decode(Finding.self, forKey: .finding))
        case "progress": return .progress(try ScanProgress(from: decoder))
        case "room_ack": return .roomAcknowledged(clientEventID: try container.decode(UUID.self, forKey: .clientEventID))
        case "scan_complete": return .scanCompleted
        case "error": return .serverError(message: try container.decodeIfPresent(String.self, forKey: .message) ?? "")
        case "pong": return .heartbeat
        default: return .unknown(type: type)
        }
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
