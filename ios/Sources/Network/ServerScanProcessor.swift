import Foundation

/// Room ids sent over the live channel. The processor maps them back to the names the
/// person gave each room.
nonisolated enum LiveRoomID {
    static let prefix = "room-"

    static func make(index: Int) -> String { "\(prefix)\(index)" }

    static func index(of roomID: String) -> Int? {
        guard roomID.hasPrefix(prefix) else { return nil }
        return Int(roomID.dropFirst(prefix.count))
    }
}

enum ScanProcessingError: Error, Equatable, LocalizedError {
    case scanNotCreatedOnServer

    var errorDescription: String? {
        "This scan was never registered with the server, so there is nothing to check yet."
    }
}

/// Waits for the background uploads of a scan, asks the server to finish it, and turns the
/// server report into the app's `ScanReport`.
final class ServerScanProcessor: ScanProcessing {
    private static let uploadShare = 0.4
    private static let assemblingFraction = 0.45
    private static let checkingFraction = 0.75

    private let api: APIClient
    private let uploader: BackgroundUploader
    private let rooms: (any RoomDelivering)?

    init(api: APIClient, uploader: BackgroundUploader, rooms: (any RoomDelivering)? = nil) {
        self.api = api
        self.uploader = uploader
        self.rooms = rooms
    }

    func process(_ manifest: ScanManifest, onUpdate: @escaping (ProcessingUpdate) -> Void) async throws -> ScanReport {
        guard let remoteScanID = manifest.remoteScanID else { throw ScanProcessingError.scanNotCreatedOnServer }
        onUpdate(ProcessingUpdate(stage: .uploading, fraction: 0))
        try await rooms?.deliverRooms(of: manifest)
        try await uploadRemainingFiles(of: remoteScanID, onUpdate: onUpdate)
        onUpdate(ProcessingUpdate(stage: .assembling, fraction: Self.assemblingFraction))
        let report = try await finishOrFetch(remoteScanID)
        onUpdate(ProcessingUpdate(stage: .checking, fraction: Self.checkingFraction))
        onUpdate(ProcessingUpdate(stage: .writing, fraction: 1))
        return Self.scanReport(from: report, manifest: manifest)
    }

    private func uploadRemainingFiles(of scanID: String, onUpdate: @escaping (ProcessingUpdate) -> Void) async throws {
        let progress = Task { [uploader] in
            for await snapshot in await uploader.updates() {
                let files = snapshot.files(forScan: scanID)
                let total = files.reduce(Int64(0)) { $0 + $1.totalBytes }
                let sent = files.reduce(Int64(0)) { $0 + $1.uploadedBytes }
                let fraction = total > 0 ? Double(sent) / Double(total) : 0
                await MainActor.run { onUpdate(ProcessingUpdate(stage: .uploading, fraction: fraction * Self.uploadShare)) }
            }
        }
        defer { progress.cancel() }
        try await uploader.waitUntilFinished(scanID: scanID)
    }

    /// A second finish while one is running or done answers 409; the stored assessment is the result.
    private func finishOrFetch(_ scanID: String) async throws -> Report {
        do {
            return try await api.finishScan(scanID: scanID)
        } catch APIError.conflict {
            return try await api.assessment(scanID: scanID)
        }
    }

    static func scanReport(from report: Report, manifest: ScanManifest) -> ScanReport {
        let roomNames = manifest.rooms.map(\.name)
        let findings = report.findings.filter { $0.asFinding != nil }
        var subjects: [String: ReportSubject] = [:]
        for finding in findings where subjects[finding.subjectID] == nil {
            subjects[finding.subjectID] = ReportSubject(
                id: finding.subjectID, roomName: roomName(for: finding, in: manifest), label: finding.title
            )
        }
        return ScanReport(
            scanID: manifest.scanID, name: manifest.name, completedAt: report.createdAt,
            roomNames: roomNames, subjects: subjects, findings: findings.compactMap(\.asFinding)
        )
    }

    private static func roomName(for finding: ServerFinding, in manifest: ScanManifest) -> String {
        guard let roomID = finding.roomID, let index = LiveRoomID.index(of: roomID),
              let room = manifest.rooms.first(where: { $0.index == index }) else { return ReportGrouping.unassignedRoom }
        return room.name
    }
}
