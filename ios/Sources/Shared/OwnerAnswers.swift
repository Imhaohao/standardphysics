import Foundation

/// An owner's answer as it goes over the wire: `true`, `42.0` or `"text"`.
nonisolated enum AnswerValue: Codable, Sendable, Equatable {
    case bool(Bool)
    case number(Double)
    case text(String)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let flag = try? container.decode(Bool.self) { self = .bool(flag) }
        else if let number = try? container.decode(Double.self) { self = .number(number) }
        else { self = .text(try container.decode(String.self)) }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .bool(let flag): try container.encode(flag)
        case .number(let number): try container.encode(number)
        case .text(let text): try container.encode(text)
        }
    }
}

/// What the owner told us about one subject, stored with the report it answers.
nonisolated struct OwnerAnswer: Codable, Sendable, Equatable {
    let subjectID: String
    let metric: String
    let value: AnswerValue
    /// The unit the owner answered in, for numbers.
    var unit: String?
    /// "photo" when the server read the answer from a photo; nil or "owner" when typed or tapped.
    var source: String?

    static let photoSource = "photo"

    var key: String { OwnerQuestions.key(subjectID: subjectID, metric: metric) }
    var isFromPhoto: Bool { source == Self.photoSource }

    enum CodingKeys: String, CodingKey {
        case subjectID = "subject_id"
        case metric, value, unit, source
    }
}

/// One entry of `PUT /v1/scans/{id}/answers`. A nil value deletes the stored answer, so it is
/// always sent, as `null`.
nonisolated struct AnswerUpdate: Encodable, Sendable, Equatable {
    let subjectID: String
    let metric: String
    let value: AnswerValue?

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(subjectID, forKey: .subjectID)
        try container.encode(metric, forKey: .metric)
        try container.encode(value, forKey: .value)
    }

    enum CodingKeys: String, CodingKey {
        case subjectID = "subject_id"
        case metric, value
    }
}

nonisolated struct AnswersRequest: Encodable, Sendable {
    let answers: [AnswerUpdate]
}

/// An answer the server holds for a scan.
nonisolated struct ServerAnswer: Decodable, Sendable, Equatable {
    let subjectID: String
    let metric: String
    let value: AnswerValue?
    /// "owner" or "photo".
    var source: String?
    var confidence: Double?
    var photoArtifactID: String?

    var asOwnerAnswer: OwnerAnswer? {
        value.map { OwnerAnswer(subjectID: subjectID, metric: metric, value: $0, source: source) }
    }

    enum CodingKeys: String, CodingKey {
        case subjectID = "subject_id"
        case metric, value, source, confidence
        case photoArtifactID = "photo_artifact_id"
    }
}

/// `POST /v1/scans/{id}/photo-answers`: read the answer to one open ask from an uploaded photo.
nonisolated struct PhotoAnswerRequest: Encodable, Sendable {
    let subjectID: String
    let metric: String
    let artifactID: String

    enum CodingKeys: String, CodingKey {
        case subjectID = "subject_id"
        case metric
        case artifactID = "artifact_id"
    }
}

/// `answered` is false when the photo was unclear; the report comes back either way.
nonisolated struct PhotoAnswerResponse: Decodable, Sendable, Equatable {
    let answered: Bool
    let answer: AnswerValue?
    let confidence: Double?
    let report: Report
}
