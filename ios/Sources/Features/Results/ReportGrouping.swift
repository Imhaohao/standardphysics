import Foundation

nonisolated struct ObjectGroup: Sendable, Equatable, Identifiable {
    let subject: ReportSubject
    let outcomes: [RuleOutcome]

    var id: String { subject.id }
    var issues: [RuleOutcome] { outcomes.filter { $0.status == .fail || $0.status == .needsInfo } }
    var worstSeverity: Int { outcomes.map(\.status.severity).max() ?? 0 }
}

nonisolated struct RoomSection: Sendable, Equatable, Identifiable {
    let name: String
    let objects: [ObjectGroup]

    var id: String { name }
    var objectsWithIssues: [ObjectGroup] { objects.filter { !$0.issues.isEmpty } }
    var passing: [(subject: ReportSubject, outcome: RuleOutcome)] {
        objects.flatMap { group in group.outcomes.filter { $0.status == .pass }.map { (group.subject, $0) } }
    }
}

nonisolated struct ReportSummary: Sendable, Equatable {
    let toFix: Int
    let questions: Int
    let passing: Int
}

nonisolated enum ReportGrouping {
    static let unassignedRoom = "Elsewhere in the space"

    static func sections(for report: ScanReport) -> [RoomSection] {
        let outcomes = RuleComparison.outcomes(from: report.findings).filter { $0.status != .notApplicable }
        let bySubject = Dictionary(grouping: outcomes, by: \.subjectID)
        let groups = bySubject.map { subjectID, outcomes in
            ObjectGroup(subject: report.subject(for: subjectID), outcomes: outcomes.sorted(by: worstFirst))
        }
        let byRoom = Dictionary(grouping: groups, by: \.subject.roomName)
        return roomOrder(report: report, present: Set(byRoom.keys)).compactMap { room in
            guard let objects = byRoom[room] else { return nil }
            return RoomSection(name: room, objects: objects.sorted(by: objectOrder))
        }
    }

    static func summary(for report: ScanReport) -> ReportSummary {
        let statuses = RuleComparison.outcomes(from: report.findings).map(\.status)
        return ReportSummary(
            toFix: statuses.filter { $0 == .fail }.count,
            questions: statuses.filter { $0 == .needsInfo }.count,
            passing: statuses.filter { $0 == .pass }.count
        )
    }

    private static func roomOrder(report: ScanReport, present: Set<String>) -> [String] {
        let known = report.roomNames.filter(present.contains)
        let extra = present.subtracting(known).sorted()
        return known + extra
    }

    private static func worstFirst(_ lhs: RuleOutcome, _ rhs: RuleOutcome) -> Bool {
        lhs.status.severity > rhs.status.severity
    }

    private static func objectOrder(_ lhs: ObjectGroup, _ rhs: ObjectGroup) -> Bool {
        if lhs.worstSeverity != rhs.worstSeverity { return lhs.worstSeverity > rhs.worstSeverity }
        return lhs.subject.label < rhs.subject.label
    }
}
