import Foundation

/// The owner's scans as the server holds them. `APIClient` is the real one.
nonisolated protocol ScanLibrary: Sendable {
    func listScans() async throws -> [ScanResponse]
    func assessment(scanID: String) async throws -> Report
    func sceneJSON(scanID: String) async throws -> String
    func answers(scanID: String) async throws -> [ServerAnswer]
    func saveAnswers(scanID: String, answers: [AnswerUpdate]) async throws -> Report
    func renameScan(scanID: String, name: String) async throws -> ScanResponse
    func deleteScan(scanID: String) async throws
    func createShare(scanID: String) async throws -> ShareResponse
}

extension APIClient: ScanLibrary {}

nonisolated struct ReportSyncPlan: Sendable, Equatable {
    /// Local reports to keep, with names the server changed applied.
    let kept: [ScanReport]
    /// Checked scans on the server this phone has no report for yet.
    let toFetch: [ScanResponse]
}

/// Lines up the reports on this phone with the scans on the owner's account.
nonisolated enum ReportSync {
    static let checkedStatus = "complete"

    /// A report from a server scan that is no longer on the account was deleted elsewhere, so it
    /// goes. Reports checked only on this phone are never touched.
    static func plan(local: [ScanReport], server: [ScanResponse]) -> ReportSyncPlan {
        let serverByID = Dictionary(server.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let kept = local.compactMap { report -> ScanReport? in
            guard let remoteScanID = report.remoteScanID else { return report }
            guard let scan = serverByID[remoteScanID] else { return nil }
            var updated = report
            updated.name = scan.name
            return updated
        }
        let held = Set(local.compactMap(\.remoteScanID))
        let toFetch = server.filter { $0.status == checkedStatus && !held.contains($0.id) }
        return ReportSyncPlan(kept: kept, toFetch: toFetch)
    }

    static func newestFirst(_ reports: [ScanReport]) -> [ScanReport] {
        reports.sorted { $0.completedAt > $1.completedAt }
    }
}

/// Turns server reports into the app's `ScanReport`.
nonisolated enum ServerReports {
    /// A scan checked on the server that this phone has no manifest for, such as one scanned on
    /// another phone. The scene, when the server has it, names the rooms and things.
    static func scanReport(scan: ScanResponse, report: Report, sceneJSON: String?) -> ScanReport {
        let roomNames = sceneJSON.map(SceneSubjects.roomNames(sceneJSON:)) ?? []
        let base = sceneJSON.map { SceneSubjects.subjects(sceneJSON: $0, roomNames: roomNames) } ?? [:]
        let findings = report.findings.filter { $0.asFinding != nil }
        let subjects = filling(base, for: findings) { finding in
            finding.roomID.flatMap { base[$0]?.roomName } ?? ReportGrouping.unassignedRoom
        }
        return ScanReport(
            scanID: UUID(uuidString: scan.id) ?? UUID(), name: scan.name, completedAt: report.createdAt,
            roomNames: roomNames, subjects: subjects, findings: findings.compactMap(\.asFinding), remoteScanID: scan.id
        )
    }

    /// The server's report after the owner answered, in place of the one shown.
    static func updating(_ existing: ScanReport, with report: Report) -> ScanReport {
        let findings = report.findings.filter { $0.asFinding != nil }
        let knownRooms = roomNamesByRoomID(findings, subjects: existing.subjects)
        let subjects = filling(existing.subjects, for: findings) { finding in
            finding.roomID.flatMap { knownRooms[$0] } ?? ReportGrouping.unassignedRoom
        }
        return existing.rechecked(findings: findings.compactMap(\.asFinding), subjects: subjects)
    }

    /// A new subject goes in the room its neighbours on the same server room are already in.
    private static func roomNamesByRoomID(_ findings: [ServerFinding], subjects: [String: ReportSubject]) -> [String: String] {
        let pairs = findings.compactMap { finding -> (String, String)? in
            guard let roomID = finding.roomID, let subject = subjects[finding.subjectID] else { return nil }
            return (roomID, subject.roomName)
        }
        return Dictionary(pairs, uniquingKeysWith: { first, _ in first })
    }

    /// Adds a subject for every finding that has none, labelled with the finding's title.
    static func filling(
        _ subjects: [String: ReportSubject], for findings: [ServerFinding], roomName: (ServerFinding) -> String
    ) -> [String: ReportSubject] {
        var filled = subjects
        for finding in findings where filled[finding.subjectID] == nil {
            filled[finding.subjectID] = ReportSubject(id: finding.subjectID, roomName: roomName(finding), label: finding.title)
        }
        return filled
    }
}
