import Foundation
@testable import StandardPhysics

/// A server account held in memory, recording what the app asked of it.
final class FakeScanLibrary: ScanLibrary, @unchecked Sendable {
    private let state = Locked(State())
    private struct State {
        var scans: [ScanResponse] = []
        var reports: [String: Report] = [:]
        var savedAnswers: [[AnswerUpdate]] = []
        var renamed: [String: String] = [:]
        var deleted: [String] = []
        var failure: APIError?
    }

    var savedAnswers: [[AnswerUpdate]] { state.read { $0.savedAnswers } }

    func hold(_ scan: ScanResponse, report: Report) {
        state.write {
            $0.scans.append(scan)
            $0.reports[scan.id] = report
        }
    }

    func failNextCalls(with error: APIError?) { state.write { $0.failure = error } }

    func listScans() async throws -> [ScanResponse] {
        try check()
        return state.read { $0.scans }
    }

    func assessment(scanID: String) async throws -> Report {
        try check()
        guard let report = state.read({ $0.reports[scanID] }) else { throw APIError.notFound }
        return report
    }

    func sceneJSON(scanID: String) async throws -> String { throw APIError.notFound }

    func answers(scanID: String) async throws -> [ServerAnswer] { [] }

    /// Answers every save with the scan's report, its findings passing now.
    func saveAnswers(scanID: String, answers: [AnswerUpdate]) async throws -> Report {
        try check()
        state.write { $0.savedAnswers.append(answers) }
        return LibraryFixtures.report(scanID: scanID, status: .pass)
    }

    var renamed: [String: String] { state.read { $0.renamed } }
    var deleted: [String] { state.read { $0.deleted } }

    func renameScan(scanID: String, name: String) async throws -> ScanResponse {
        try check()
        state.write { $0.renamed[scanID] = name }
        return LibraryFixtures.scan(scanID, name: name)
    }

    func deleteScan(scanID: String) async throws {
        try check()
        state.write { $0.deleted.append(scanID) }
    }

    func createShare(scanID: String) async throws -> ShareResponse {
        try check()
        return ShareResponse(token: "tok_\(scanID.prefix(4))", createdAt: fixedNow)
    }

    private func check() throws {
        if let failure = state.read({ $0.failure }) { throw failure }
    }
}

nonisolated enum LibraryFixtures {
    static let scanID = "6f1c3a52-0000-4000-8000-000000000001"
    static let ask = FindingAsk(metric: "door.opening_force", prompt: "How hard is it to push?", valueType: .number, unit: "lbf")

    static func scan(_ id: String = scanID, name: String = "Corner Deli") -> ScanResponse {
        ScanResponse(id: id, name: name, siteName: nil, status: "complete", createdAt: fixedNow, updatedAt: fixedNow)
    }

    static func report(scanID: String = scanID, status: FindingStatus = .needsInfo) -> Report {
        var finding = ServerFindingFixture.make(ruleID: "ADA-404.2.9", subjectID: "door-1", status: status)
        finding.ask = status == .needsInfo ? ask : nil
        return Report(
            scanID: scanID, assessmentID: "a1", createdAt: fixedNow, summary: ServerFindingFixture.summary, findings: [finding],
            timings: StageTimings(loadMs: 0, labellingMs: 0, evaluationMs: 0, persistMs: 0, totalMs: 0),
            labelledByVision: 0, unlabelledObjects: 0
        )
    }
}
