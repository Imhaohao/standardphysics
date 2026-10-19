import Foundation

/// Journal operations the capture flow needs beyond the shared contract.
nonisolated protocol ScanRetaining: Sendable {
    func releaseHeavyFiles(scanID: UUID) async throws
}

nonisolated protocol ScanStore: ScanJournaling, ScanRetaining {
    func delete(scanID: UUID) async throws
    func saveMesh(scanID: UUID, data: Data) async throws -> ScanManifest
    /// Mesh carried over from before the last relaunch, merged into every later export.
    func carriedOverMesh(scanID: UUID) async -> Data?
    /// Called once per relaunch: whatever mesh is on disk becomes the carried-over base.
    func carryOverMesh(scanID: UUID) async throws
    func frameLog(scanID: UUID) async -> FrameLog
    func saveFrameLog(_ log: FrameLog, scanID: UUID) async throws
}

nonisolated enum ScanJournalError: Error, Equatable {
    case unsupportedVersion(Int)
}

nonisolated enum ScanFiles {
    static let manifest = "manifest.json"
    static let roomsDirectory = "rooms"
    static let worldMap = "worldmap.arworldmap"
    static let relocalizationSnapshot = "relocalize.jpg"
    static let mesh = "mesh.spm"
    static let carriedOverMesh = "mesh-base.spm"
    static let frameLog = "frames.json"

    static let heavy = [mesh, carriedOverMesh, worldMap, relocalizationSnapshot]

    static func room(_ index: Int) -> String { "\(roomsDirectory)/\(index).json" }
}

/// `Application Support/Scans/<uuid>/`. Every file is written atomically and rooms are written
/// before the manifest that lists them, so a kill at any instant leaves a loadable scan.
actor FileScanJournal: ScanStore {
    nonisolated static var defaultRoot: URL {
        URL.applicationSupportDirectory.appending(path: "Scans", directoryHint: .isDirectory)
    }

    nonisolated let root: URL
    private let writer: any AtomicFileWriting

    init(root: URL = FileScanJournal.defaultRoot, writer: any AtomicFileWriting = AtomicFileWriter()) {
        self.root = root
        self.writer = writer
    }

    nonisolated func directory(for scanID: UUID) -> URL {
        root.appending(path: scanID.uuidString, directoryHint: .isDirectory)
    }

    func create(name: String) async throws -> ScanManifest {
        let manifest = ScanManifest(scanID: UUID(), name: name, startedAt: .now, phase: .idle, rooms: [])
        try ProtectedDirectory.create(root, excludingFromBackup: true)
        try ProtectedDirectory.create(directory(for: manifest.scanID).appending(path: ScanFiles.roomsDirectory))
        try write(manifest)
        return manifest
    }

    func load(scanID: UUID) async throws -> ScanManifest {
        removeTemporaryFiles(of: scanID)
        let stored = try readManifest(scanID: scanID)
        let recovered = adoptingOrphanRooms(stored)
        if recovered != stored {
            try write(recovered)
        }
        return recovered
    }

    func unfinishedScans() async throws -> [ScanManifest] {
        let entries = (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? []
        var manifests: [ScanManifest] = []
        for scanID in entries.compactMap({ UUID(uuidString: $0.lastPathComponent) }) {
            guard let manifest = try? await load(scanID: scanID), Self.isResumable(manifest) else { continue }
            manifests.append(manifest)
        }
        return manifests.sorted { $0.startedAt > $1.startedAt }
    }

    func update(_ manifest: ScanManifest) async throws {
        try write(manifest)
    }

    func appendRoom(scanID: UUID, capturedRoomJSON: Data, name: String) async throws -> ScanManifest {
        var manifest = try readManifest(scanID: scanID)
        let index = manifest.rooms.count
        try writer.write(capturedRoomJSON, to: url(scanID, ScanFiles.room(index)))
        manifest.rooms.append(RoomRecord(index: index, name: name, capturedRoomFile: ScanFiles.room(index), completedAt: .now))
        try write(manifest)
        return manifest
    }

    func saveWorldMap(scanID: UUID, data: Data, snapshotJPEG: Data?) async throws -> ScanManifest {
        var manifest = try readManifest(scanID: scanID)
        try writer.write(data, to: url(scanID, ScanFiles.worldMap), protection: .complete)
        manifest.worldMapFile = ScanFiles.worldMap
        manifest.worldMapSavedAt = .now
        if let snapshotJPEG {
            try writer.write(snapshotJPEG, to: url(scanID, ScanFiles.relocalizationSnapshot), protection: .complete)
            manifest.relocalizationSnapshotFile = ScanFiles.relocalizationSnapshot
        }
        try write(manifest)
        return manifest
    }

    func saveMesh(scanID: UUID, data: Data) async throws -> ScanManifest {
        var manifest = try readManifest(scanID: scanID)
        try writer.write(data, to: url(scanID, ScanFiles.mesh))
        manifest.meshFile = ScanFiles.mesh
        try write(manifest)
        return manifest
    }

    func carriedOverMesh(scanID: UUID) async -> Data? {
        try? Data(contentsOf: url(scanID, ScanFiles.carriedOverMesh))
    }

    func carryOverMesh(scanID: UUID) async throws {
        let mesh = url(scanID, ScanFiles.mesh)
        guard FileManager.default.fileExists(atPath: mesh.path) else { return }
        try writer.write(try Data(contentsOf: mesh), to: url(scanID, ScanFiles.carriedOverMesh))
    }

    func frameLog(scanID: UUID) async -> FrameLog {
        guard let data = try? Data(contentsOf: url(scanID, ScanFiles.frameLog)) else { return FrameLog() }
        return (try? JSONDecoder().decode(FrameLog.self, from: data)) ?? FrameLog()
    }

    func saveFrameLog(_ log: FrameLog, scanID: UUID) async throws {
        try writer.write(try JSONEncoder().encode(log), to: url(scanID, ScanFiles.frameLog))
    }

    /// Once the server holds the finished scan, the mesh, world map and camera snapshot only
    /// take up space and carry a picture of the shop, so they go. Rooms and the manifest stay.
    func releaseHeavyFiles(scanID: UUID) async throws {
        var manifest = try readManifest(scanID: scanID)
        for file in ScanFiles.heavy {
            try? FileManager.default.removeItem(at: url(scanID, file))
        }
        manifest.meshFile = nil
        manifest.worldMapFile = nil
        manifest.relocalizationSnapshotFile = nil
        try write(manifest)
    }

    func delete(scanID: UUID) async throws {
        let directory = directory(for: scanID)
        guard FileManager.default.fileExists(atPath: directory.path) else { return }
        try FileManager.default.removeItem(at: directory)
    }

    // MARK: Private

    nonisolated private static func isResumable(_ manifest: ScanManifest) -> Bool {
        if manifest.phase == .finished { return false }
        return !(manifest.phase == .idle && manifest.rooms.isEmpty)
    }

    private func url(_ scanID: UUID, _ file: String) -> URL {
        directory(for: scanID).appending(path: file)
    }

    private func readManifest(scanID: UUID) throws -> ScanManifest {
        let data = try Data(contentsOf: url(scanID, ScanFiles.manifest))
        let manifest = try JSONDecoder().decode(ScanManifest.self, from: data)
        guard manifest.version <= ScanManifest.currentVersion else {
            throw ScanJournalError.unsupportedVersion(manifest.version)
        }
        return manifest
    }

    private func write(_ manifest: ScanManifest) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        try writer.write(try encoder.encode(manifest), to: url(manifest.scanID, ScanFiles.manifest))
    }

    /// A room file is written before the manifest lists it. If the app died in between, the
    /// room is complete on disk and is adopted instead of being lost.
    private func adoptingOrphanRooms(_ manifest: ScanManifest) -> ScanManifest {
        var recovered = manifest
        while let record = orphanRoom(scanID: manifest.scanID, index: recovered.rooms.count) {
            recovered.rooms.append(record)
        }
        guard recovered.rooms.count > manifest.rooms.count else { return manifest }
        if Self.isMidRoom(recovered.phase) {
            recovered.phase = .betweenRooms(completed: recovered.rooms.count)
        }
        return recovered
    }

    private func orphanRoom(scanID: UUID, index: Int) -> RoomRecord? {
        let file = url(scanID, ScanFiles.room(index))
        guard let data = try? Data(contentsOf: file), (try? JSONSerialization.jsonObject(with: data)) != nil else {
            return nil
        }
        let modified = (try? file.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate
        return RoomRecord(index: index, name: "Room \(index + 1)", capturedRoomFile: ScanFiles.room(index), completedAt: modified ?? .now)
    }

    nonisolated private static func isMidRoom(_ phase: CapturePhase) -> Bool {
        switch phase {
        case .scanning, .paused, .relocalizing, .betweenRooms: true
        default: false
        }
    }

    private func removeTemporaryFiles(of scanID: UUID) {
        let directory = directory(for: scanID)
        for folder in [directory, directory.appending(path: ScanFiles.roomsDirectory)] {
            let entries = (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)) ?? []
            for entry in entries where AtomicFileWriter.isTemporaryFile(entry) {
                try? FileManager.default.removeItem(at: entry)
            }
        }
    }
}
