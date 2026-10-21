import Foundation
import Observation

enum AppRoute: Equatable {
    case home
    case beforeYouScan
    case capture
    case processing
    case results(UUID)
}

enum PhotoAnswerOutcome: Equatable {
    case answered
    /// The server couldn't tell from the photo; retake it or answer by hand.
    case unclear
    /// The server can't read photos yet (409); answer by hand.
    case unavailable
    case failed
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
    /// False on a phone without LiDAR: it can't scan, but it can still show the account's reports.
    let canScan: Bool
    private let processor: any ScanProcessing
    private let journal: (any ScanJournaling)?
    private let reportStore: (any ReportStoring)?
    private let library: (any ScanLibrary)?
    private let recheck: (any ReportRechecking)?
    /// The web app, for read-only report links; nil hides them.
    private let webBaseURL: URL?
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
        webBaseURL: URL? = nil,
        canScan: Bool = true,
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
        self.webBaseURL = webBaseURL
        self.canScan = canScan
        self.unfinishedScans = unfinishedScans
        self.reports = reports
        account.onAccountDeleted = { [weak self] in await self?.forgetServerReports() }
    }

    /// The account and its scans are gone from the server, so their copies leave the phone too.
    /// Reports checked only on this phone stay.
    func forgetServerReports() async {
        await commit(reports.filter { $0.remoteScanID == nil })
        if case .results(let scanID) = route, report(id: scanID) == nil { route = .home }
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
        guard canScan else { return }
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

    // MARK: Sharing

    static let linkNotMade = "We couldn't make a link right now. Check your connection and try again."

    /// Links need the web app's address, a scan the server holds, and a signed-in owner.
    func canShareLink(for report: ScanReport) -> Bool {
        webBaseURL != nil && library != nil && report.remoteScanID != nil && account.state.isSignedIn
    }

    func makeShareLink(for scanID: UUID) async -> URL? {
        guard let webBaseURL, let library, let remoteScanID = report(id: scanID)?.remoteScanID else { return nil }
        do {
            let share = try await library.createShare(scanID: remoteScanID)
            notice = nil
            return WebLinks.sharedReportURL(base: webBaseURL, token: share.token)
        } catch {
            notice = Self.linkNotMade
            return nil
        }
    }

    // MARK: Rename and delete

    static let renameNotSent = "We couldn't rename this on your account, so the old name stays for now. Check your connection and try again."
    static let deleteNotSent = "We couldn't delete this from your account, so it's still here. Check your connection and try again."

    func renameReport(_ scanID: UUID, to name: String) async {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, var report = report(id: scanID), report.name != trimmed else { return }
        if let remoteScanID = report.remoteScanID {
            let renamed = await runOnServer(failure: Self.renameNotSent) { _ = try await $0.renameScan(scanID: remoteScanID, name: trimmed) }
            guard renamed else { return }
        }
        report.name = trimmed
        await replace(report)
    }

    /// A server scan is deleted on the account first, so a failure leaves both copies in place.
    func deleteReport(_ scanID: UUID) async {
        guard let report = report(id: scanID) else { return }
        if let remoteScanID = report.remoteScanID {
            let deleted = await runOnServer(failure: Self.deleteNotSent) { try await $0.deleteScan(scanID: remoteScanID) }
            guard deleted else { return }
        }
        await capture.deleteScan(scanID: scanID)
        await commit(reports.filter { $0.scanID != scanID })
        if route == .results(scanID) { route = .home }
    }

    /// An unfinished scan is gone from the phone whatever the server says; the server's half of it
    /// was never checked, so a failed delete there costs nothing.
    func deleteUnfinishedScan(_ scanID: UUID) async {
        guard let scan = unfinishedScans.first(where: { $0.scanID == scanID }) else { return }
        await capture.deleteScan(scanID: scanID)
        unfinishedScans.removeAll { $0.scanID == scanID }
        if let remoteScanID = scan.remoteScanID, let library {
            try? await library.deleteScan(scanID: remoteScanID)
        }
    }

    /// True when the server did it, or the scan was already gone from the account.
    private func runOnServer(failure: String, _ work: (any ScanLibrary) async throws -> Void) async -> Bool {
        guard let library else {
            notice = failure
            return false
        }
        do {
            try await work(library)
        } catch APIError.notFound {
            return true
        } catch {
            notice = failure
            return false
        }
        notice = nil
        return true
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

    // MARK: Photo answers

    static let photoNotSent = "We couldn't send that photo. Check your connection and try again, or answer by hand."

    /// Turns false for the rest of the session once the server says it can't read photos yet.
    private(set) var isPhotoReadingAvailable = true

    /// Offered on a signed-in server scan when the rule says a photo would settle it.
    func canAnswerWithPhoto(_ question: OwnerQuestion, inReport reportID: UUID) -> Bool {
        question.ask.photo && isPhotoReadingAvailable && library != nil && account.state.isSignedIn
            && report(id: reportID)?.remoteScanID != nil
    }

    /// Uploads the photo, asks the server to read the answer from it, and shows the re-checked
    /// report. An unclear photo still returns the report, with the question left open.
    func answerWithPhoto(_ question: OwnerQuestion, jpeg: Data, inReport reportID: UUID) async -> PhotoAnswerOutcome {
        guard let library, let remoteScanID = report(id: reportID)?.remoteScanID else { return .failed }
        do {
            let artifactID = try await library.uploadPhoto(jpeg: jpeg, scanID: remoteScanID)
            let result = try await library.answerFromPhoto(
                scanID: remoteScanID, subjectID: question.subjectID, metric: question.ask.metric, artifactID: artifactID
            )
            await applyPhotoAnswer(result, to: question, inReport: reportID)
            notice = nil
            return result.answered ? .answered : .unclear
        } catch APIError.conflict {
            isPhotoReadingAvailable = false
            return .unavailable
        } catch {
            notice = Self.photoNotSent
            return .failed
        }
    }

    private func applyPhotoAnswer(_ result: PhotoAnswerResponse, to question: OwnerQuestion, inReport reportID: UUID) async {
        guard let current = report(id: reportID) else { return }
        var updated = ServerReports.updating(current, with: result.report)
        if result.answered, let value = result.answer {
            updated.answers = OwnerQuestions.setting(value, for: question, in: updated.answers, source: OwnerAnswer.photoSource)
        }
        await replace(updated)
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
