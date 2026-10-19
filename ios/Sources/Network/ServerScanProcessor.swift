import Foundation

/// The id the server files a room under, whether it arrives over the live channel or as an
/// uploaded file: the CapturedRoom `identifier`, or the uploaded file's name without its
/// extension. Both paths must agree or the server stores the room twice.
nonisolated enum RoomIdentity {
    static func roomID(capturedRoomJSON: Data, fileName: String) -> String {
        if let object = try? JSONSerialization.jsonObject(with: capturedRoomJSON) as? [String: Any],
           let identifier = object["identifier"] as? String, !identifier.isEmpty {
            return identifier
        }
        return (fileName as NSString).deletingPathExtension
    }

    static func roomID(of record: RoomRecord, in directory: URL) -> String {
        let url = directory.appending(path: record.capturedRoomFile)
        let data = (try? Data(contentsOf: url)) ?? Data()
        return roomID(capturedRoomJSON: data, fileName: url.lastPathComponent)
    }

    /// Owner room names keyed by server room id.
    static func names(of manifest: ScanManifest, in directory: URL) -> [String: String] {
        Dictionary(
            manifest.rooms.map { (roomID(of: $0, in: directory), $0.name) },
            uniquingKeysWith: { first, _ in first }
        )
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
    private let retention: (any ScanRetaining)?
    private let roomDirectory: ((UUID) -> URL)?

    init(
        api: APIClient,
        uploader: BackgroundUploader,
        rooms: (any RoomDelivering)? = nil,
        retention: (any ScanRetaining)? = nil,
        roomDirectory: ((UUID) -> URL)? = nil
    ) {
        self.api = api
        self.uploader = uploader
        self.rooms = rooms
        self.retention = retention
        self.roomDirectory = roomDirectory
    }

    func process(_ manifest: ScanManifest, onUpdate: @escaping (ProcessingUpdate) -> Void) async throws -> ScanReport {
        guard let remoteScanID = manifest.remoteScanID else { throw ScanProcessingError.scanNotCreatedOnServer }
        onUpdate(ProcessingUpdate(stage: .uploading, fraction: 0))
        try await rooms?.deliverRooms(of: manifest)
        try await uploadRemainingFiles(of: remoteScanID, onUpdate: onUpdate)
        onUpdate(ProcessingUpdate(stage: .assembling, fraction: Self.assemblingFraction))
        let report = try await finishOrFetch(remoteScanID)
        onUpdate(ProcessingUpdate(stage: .checking, fraction: Self.checkingFraction))
        try? await retention?.releaseHeavyFiles(scanID: manifest.scanID)
        onUpdate(ProcessingUpdate(stage: .writing, fraction: 1))
        let roomNamesByID = roomDirectory.map { RoomIdentity.names(of: manifest, in: $0(manifest.scanID)) } ?? [:]
        return Self.scanReport(from: report, manifest: manifest, roomNamesByID: roomNamesByID)
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

    static func scanReport(from report: Report, manifest: ScanManifest, roomNamesByID: [String: String] = [:]) -> ScanReport {
        let roomNames = manifest.rooms.map(\.name)
        let findings = report.findings.filter { $0.asFinding != nil }
        var subjects: [String: ReportSubject] = [:]
        for finding in findings where subjects[finding.subjectID] == nil {
            subjects[finding.subjectID] = ReportSubject(
                id: finding.subjectID, roomName: finding.roomID.flatMap { roomNamesByID[$0] } ?? ReportGrouping.unassignedRoom,
                label: finding.title
            )
        }
        return ScanReport(
            scanID: manifest.scanID, name: manifest.name, completedAt: report.createdAt,
            roomNames: roomNames, subjects: subjects, findings: findings.compactMap(\.asFinding)
        )
    }
}
