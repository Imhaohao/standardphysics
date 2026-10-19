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

    let capture: any CaptureControlling
    private let processor: any ScanProcessing
    private let journal: (any ScanJournaling)?

    init(
        capture: any CaptureControlling,
        processor: any ScanProcessing,
        journal: (any ScanJournaling)? = nil,
        unfinishedScans: [ScanManifest] = [],
        reports: [ScanReport] = []
    ) {
        self.capture = capture
        self.processor = processor
        self.journal = journal
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
        guard let journal, let scans = try? await journal.unfinishedScans() else { return }
        unfinishedScans = scans.sorted { $0.startedAt > $1.startedAt }
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
            reports.removeAll { $0.scanID == report.scanID }
            reports.insert(report, at: 0)
            processing = nil
            route = .results(report.scanID)
        } catch {
            processing?.failure = "We couldn't finish checking this scan. Your rooms are saved on this phone, so check your connection and try again."
        }
    }
}
