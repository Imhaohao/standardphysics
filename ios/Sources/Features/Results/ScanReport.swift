import Foundation

/// What a finding is about, as the person scanning would recognise it.
nonisolated struct ReportSubject: Codable, Sendable, Equatable {
    let id: String
    let roomName: String
    let label: String
}

nonisolated struct ScanReport: Codable, Sendable, Equatable, Identifiable {
    let scanID: UUID
    var name: String
    let completedAt: Date
    let roomNames: [String]
    var subjects: [String: ReportSubject]
    var findings: [Finding]
    /// The server's id for this scan when the server checked it, so changes go back to it.
    var remoteScanID: String? = nil

    var id: UUID { scanID }

    func subject(for id: String) -> ReportSubject {
        subjects[id] ?? ReportSubject(id: id, roomName: ReportGrouping.unassignedRoom, label: id)
    }

    enum CodingKeys: String, CodingKey {
        case scanID, name, completedAt, roomNames, subjects, findings, remoteScanID
    }
}

extension ScanReport {
    /// Reports saved before a field existed still load.
    nonisolated init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        scanID = try container.decode(UUID.self, forKey: .scanID)
        name = try container.decode(String.self, forKey: .name)
        completedAt = try container.decode(Date.self, forKey: .completedAt)
        roomNames = try container.decode([String].self, forKey: .roomNames)
        subjects = try container.decode([String: ReportSubject].self, forKey: .subjects)
        findings = try container.decode([Finding].self, forKey: .findings)
        remoteScanID = try container.decodeIfPresent(String.self, forKey: .remoteScanID)
    }
}

nonisolated enum ScanLimits {
    static let maxRooms = 8
}
