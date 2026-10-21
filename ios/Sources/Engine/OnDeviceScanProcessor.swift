import Foundation

nonisolated enum OnDeviceProcessingError: Error, Equatable {
    case noRooms
    case unreadableRoom(String)
}

/// Checks a finished scan entirely on the phone: every saved room goes through a fresh engine,
/// then the whole space is evaluated at once so routes between rooms are checked too.
final class OnDeviceScanProcessor: ScanProcessing {
    private let journal: any ScanJournaling
    private let makeEngine: @Sendable () throws -> any RoomComplianceEvaluating

    init(
        journal: any ScanJournaling,
        makeEngine: @escaping @Sendable () throws -> any RoomComplianceEvaluating = { try RustComplianceEngine() }
    ) {
        self.journal = journal
        self.makeEngine = makeEngine
    }

    func process(_ manifest: ScanManifest, onUpdate: @escaping (ProcessingUpdate) -> Void) async throws -> ScanReport {
        try await process(manifest, answers: [], onUpdate: onUpdate)
    }

    /// Checks the scan again from its saved rooms, this time with what the owner answered.
    func recheck(scanID: UUID, answers: [OwnerAnswer]) async throws -> ScanReport {
        let manifest = try await journal.load(scanID: scanID)
        return try await process(manifest, answers: answers) { _ in }
    }

    func process(
        _ manifest: ScanManifest, answers: [OwnerAnswer], onUpdate: @escaping (ProcessingUpdate) -> Void
    ) async throws -> ScanReport {
        guard !manifest.rooms.isEmpty else { throw OnDeviceProcessingError.noRooms }
        onUpdate(ProcessingUpdate(stage: .assembling, fraction: 0.1))
        let rooms = try await loadRooms(of: manifest)

        onUpdate(ProcessingUpdate(stage: .checking, fraction: 0.4))
        let engine = try makeEngine()
        for room in rooms {
            _ = try await engine.evaluateRoom(capturedRoomJSON: room.json, detectedObjects: room.detectedObjects)
        }
        try await engine.addOwnerAnswers(answers)
        let result = try await engine.evaluateScan()

        onUpdate(ProcessingUpdate(stage: .writing, fraction: 0.9))
        let report = Self.report(for: manifest, from: result)
        onUpdate(ProcessingUpdate(stage: .writing, fraction: 1))
        return report
    }

    private func loadRooms(of manifest: ScanManifest) async throws -> [(json: Data, detectedObjects: [DetectedObject])] {
        let directory = journal.directory(for: manifest.scanID)
        return try manifest.rooms.sorted { $0.index < $1.index }.map { record in
            let url = directory.appending(path: record.capturedRoomFile)
            guard let data = try? Data(contentsOf: url) else {
                throw OnDeviceProcessingError.unreadableRoom(record.capturedRoomFile)
            }
            return (data, DetectedObjectFile.objects(forRoomAt: url))
        }
    }

    static func report(for manifest: ScanManifest, from result: ComplianceReport) -> ScanReport {
        let roomNames = manifest.rooms.sorted { $0.index < $1.index }.map(\.name)
        var subjects = SceneSubjects.subjects(sceneJSON: result.sceneJSON, roomNames: roomNames)
        for finding in result.findings where subjects[finding.subjectID] == nil {
            subjects[finding.subjectID] = SceneSubjects.fallback(
                for: finding.subjectID,
                roomID: result.findingRooms[finding.id],
                in: subjects
            )
        }
        return ScanReport(
            scanID: manifest.scanID,
            name: manifest.name,
            completedAt: .now,
            roomNames: roomNames,
            subjects: subjects,
            findings: result.findings
        )
    }
}
