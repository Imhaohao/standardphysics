import Foundation
import Observation

enum AppRoute: Equatable {
    case home
    case beforeYouScan
    case capture
    case processing
    case results(UUID)
}

struct ProcessingState: Equatable {
    var stage: ProcessingStage = .uploading
    var fraction: Double = 0
    let startedAt: Date
    var failure: String?
}

@Observable
final class AppModel {
    var route: AppRoute = .home
    private(set) var unfinishedScans: [ScanManifest]
    private(set) var reports: [ScanReport]
    private(set) var processing: ProcessingState?
    private(set) var answers: [String: Bool] = [:]
    /// Something that didn't go through, such as an answer the server didn't get.
    private(set) var notice: String?

    let capture: any CaptureControlling
    let account: AccountModel
    private let processor: any ScanProcessing
    private let journal: (any ScanJournaling)?
    private let reportStore: (any ReportStoring)?
    private let library: (any ScanLibrary)?
    private let recheck: (any ReportRechecking)?
    @ObservationIgnored private var hasLoadedStoredReports = false

    static let answerNotSent = "Your answer is saved on this phone, but it didn't reach the server, so the report hasn't been checked again yet. Check your connection and answer again."

    init(
        capture: any CaptureControlling,
        processor: any ScanProcessing,
        journal: (any ScanJournaling)? = nil,
        account: AccountModel = AccountModel(service: nil),
        reportStore: (any ReportStoring)? = nil,
        library: (any ScanLibrary)? = nil,
        recheck: (any ReportRechecking)? = nil,
        unfinishedScans: [ScanManifest] = [],
        reports: [ScanReport] = []
    ) {
        self.capture = capture
        self.processor = processor
        self.journal = journal
        self.account = account
        self.reportStore = reportStore
        self.library = library
        self.recheck = recheck
        self.unfinishedScans = unfinishedScans
        self.reports = reports
    }

    var completedRooms: Int {
        capture.manifest?.rooms.count ?? 0
    }

    var canAddRoom: Bool {
        completedRooms < ScanLimits.maxRooms
    }

    func report(id: UUID) -> ScanReport? {
        reports.first { $0.scanID == id }
    }

    func refresh() async {
        await loadStoredReports()
        await refreshUnfinishedScans()
        await syncServerReports()
    }

    private func refreshUnfinishedScans() async {
        guard let journal, let scans = try? await journal.unfinishedScans() else { return }
        unfinishedScans = scans.sorted { $0.startedAt > $1.startedAt }
    }

    /// Reports on disk join whatever is already in memory, once per launch.
    private func loadStoredReports() async {
        guard let reportStore, !hasLoadedStoredReports else { return }
        hasLoadedStoredReports = true
        let stored = await reportStore.loadAll()
        let inMemory = Set(reports.map(\.scanID))
        reports = ReportSync.newestFirst(reports + stored.filter { !inMemory.contains($0.scanID) })
    }

    /// Signed in, the account's checked scans join the list, including ones scanned on another
    /// phone, and scans deleted elsewhere leave it.
    private func syncServerReports() async {
        guard let library, account.state.isSignedIn, let scans = try? await library.listScans() else { return }
        var fetched: [ScanReport] = []
        for scan in ReportSync.plan(local: reports, server: scans).toFetch {
            if let report = await serverReport(for: scan, from: library) { fetched.append(report) }
        }
        let plan = ReportSync.plan(local: reports, server: scans)
        let held = Set(plan.kept.compactMap(\.remoteScanID))
        await commit(ReportSync.newestFirst(plan.kept + fetched.filter { !held.contains($0.remoteScanID ?? "") }))
    }

    private func serverReport(for scan: ScanResponse, from library: any ScanLibrary) async -> ScanReport? {
        guard let assessment = try? await library.assessment(scanID: scan.id) else { return nil }
        let scene = try? await library.sceneJSON(scanID: scan.id)
        var report = ServerReports.scanReport(scan: scan, report: assessment, sceneJSON: scene)
        let stored = (try? await library.answers(scanID: scan.id)) ?? []
        report.answers = stored.compactMap(\.asOwnerAnswer)
        return report
    }

    /// Replaces the reports and writes only what changed to disk.
    private func commit(_ updated: [ScanReport]) async {
        let previous = Dictionary(reports.map { ($0.scanID, $0) }, uniquingKeysWith: { first, _ in first })
        reports = updated
        guard let reportStore else { return }
        let keptIDs = Set(updated.map(\.scanID))
        for report in updated where previous[report.scanID] != report {
            try? await reportStore.save(report)
        }
        for scanID in previous.keys where !keptIDs.contains(scanID) {
            try? await reportStore.delete(scanID: scanID)
        }
    }

    private func replace(_ report: ScanReport) async {
        await commit(reports.map { $0.scanID == report.scanID ? report : $0 })
    }

    func startNewScan() {
        route = .beforeYouScan
    }

    func beginScanning(name: String) async {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        await capture.startScan(name: trimmed.isEmpty ? "Untitled scan" : trimmed)
        route = .capture
    }

    /// Picking an unfinished scan skips the briefing: the person has scanned here before, and the
    /// first thing they need is to line the camera back up.
    func continueScan(_ scanID: UUID) async {
        await capture.resume(scanID: scanID)
        route = .capture
    }

    func finishRoom() async {
        await capture.finishRoom()
    }

    func nameRoom(index: Int, name: String) async {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        await capture.nameRoom(index: index, name: trimmed)
    }

    func scanAnotherRoom() {
        guard canAddRoom else { return }
        capture.startNextRoom()
    }

    func finishScan() async {
        await capture.finishScan()
        guard let manifest = capture.manifest else {
            route = .home
            return
        }
        unfinishedScans.removeAll { $0.scanID == manifest.scanID }
        await process(manifest)
    }

    func retryProcessing() async {
        guard let manifest = capture.manifest else { return }
        await process(manifest)
    }

    func leaveCapture() async {
        capture.pause()
        if let manifest = capture.manifest, !unfinishedScans.contains(where: { $0.scanID == manifest.scanID }) {
            unfinishedScans.insert(manifest, at: 0)
        }
        route = .home
        await refresh()
    }

    func openReport(_ id: UUID) {
        route = .results(id)
    }

    func goHome() {
        route = .home
    }

    func answer(_ outcomeID: String, yes: Bool) {
        answers[outcomeID] = yes
    }

    func dismissNotice() {
        notice = nil
    }

    // MARK: Owner answers

    func answer(to question: OwnerQuestion, inReport reportID: UUID) -> AnswerValue? {
        report(id: reportID).flatMap { OwnerQuestions.answer(to: question, in: $0.answers)?.value }
    }

    /// Saves the answer with the report straight away, then has the report checked again: by the
    /// server for a server scan, on the phone otherwise. A nil value clears the answer.
    func answer(_ question: OwnerQuestion, with value: AnswerValue?, inReport reportID: UUID) async {
        guard var report = report(id: reportID) else { return }
        report.answers = OwnerQuestions.setting(value, for: question, in: report.answers)
        await replace(report)
        if let remoteScanID = report.remoteScanID {
            await sendAnswers(of: report, to: remoteScanID, clearing: value == nil ? question : nil)
        } else {
            await recheckOnPhone(report)
        }
    }

    private func sendAnswers(of report: ScanReport, to remoteScanID: String, clearing cleared: OwnerQuestion?) async {
        guard let library else { return }
        let updates = OwnerQuestions.updates(for: report.answers, clearing: cleared)
        do {
            let fresh = try await library.saveAnswers(scanID: remoteScanID, answers: updates)
            await applyRecheck(of: report) { ServerReports.updating($0, with: fresh) }
            notice = nil
        } catch {
            notice = Self.answerNotSent
        }
    }

    private func recheckOnPhone(_ report: ScanReport) async {
        guard let recheck, let fresh = try? await recheck.recheck(scanID: report.scanID, answers: report.answers) else { return }
        await applyRecheck(of: report) { $0.rechecked(findings: fresh.findings, subjects: fresh.subjects) }
    }

    /// A check that comes back after the owner changed another answer is out of date; the check
    /// for the later answers replaces the report instead.
    private func applyRecheck(of sent: ScanReport, _ update: (ScanReport) -> ScanReport) async {
        guard let current = report(id: sent.scanID), current.answers == sent.answers else { return }
        await replace(update(current))
    }

    /// Freezes the processing screen part-way through, for previews and screenshots.
    func stageProcessing() {
        processing = ProcessingState(stage: .checking, fraction: 0.62, startedAt: Date(timeIntervalSinceNow: -24))
        route = .processing
    }

    private func process(_ manifest: ScanManifest) async {
        processing = ProcessingState(startedAt: .now)
        route = .processing
        do {
            let report = try await processor.process(manifest) { [weak self] update in
                self?.processing?.stage = update.stage
                self?.processing?.fraction = update.fraction
            }
            await commit([report] + reports.filter { $0.scanID != report.scanID })
            processing = nil
            route = .results(report.scanID)
        } catch {
            processing?.failure = "We couldn't finish checking this scan. Your rooms are saved on this phone, so check your connection and try again."
        }
    }
}
