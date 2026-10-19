import Foundation

/// What a finding is about, as the person scanning would recognise it.
nonisolated struct ReportSubject: Codable, Sendable, Equatable {
    let id: String
    let roomName: String
    let label: String
}

nonisolated struct ScanReport: Codable, Sendable, Equatable, Identifiable {
    let scanID: UUID
    let name: String
    let completedAt: Date
    let roomNames: [String]
    let subjects: [String: ReportSubject]
    let findings: [Finding]

    var id: UUID { scanID }

    func subject(for id: String) -> ReportSubject {
        subjects[id] ?? ReportSubject(id: id, roomName: ReportGrouping.unassignedRoom, label: id)
    }
}

nonisolated enum ScanLimits {
    static let maxRooms = 8
}
