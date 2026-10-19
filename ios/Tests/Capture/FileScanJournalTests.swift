import XCTest
@testable import StandardPhysics

private struct SimulatedCrash: Error {}

/// Lets the first `survivingWrites` writes through, then dies mid-write leaving a partial temp
/// file behind (or, for odd crash points, a complete temp file that was never renamed).
private final class CrashingWriter: AtomicFileWriting, @unchecked Sendable {
    private let survivingWrites: Int
    private let lock = NSLock()
    private var writes = 0
    private let real = AtomicFileWriter()

    init(survivingWrites: Int) {
        self.survivingWrites = survivingWrites
    }

    func write(_ data: Data, to url: URL, protection: FileProtectionType) throws {
        let count = lock.withLock { () -> Int in
            writes += 1
            return writes
        }
        guard count > survivingWrites else {
            try real.write(data, to: url, protection: protection)
            return
        }
        let leftover = count.isMultiple(of: 2) ? data.prefix(data.count / 2) : data
        try leftover.write(to: AtomicFileWriter.temporaryURL(for: url))
        throw SimulatedCrash()
    }
}

private final class CountingWriter: AtomicFileWriting, @unchecked Sendable {
    private let lock = NSLock()
    private var writes = 0
    private let real = AtomicFileWriter()

    var count: Int { lock.withLock { writes } }

    func write(_ data: Data, to url: URL, protection: FileProtectionType) throws {
        lock.withLock { writes += 1 }
        try real.write(data, to: url, protection: protection)
    }
}

private final class ProtectionRecorder: AtomicFileWriting, @unchecked Sendable {
    private let lock = NSLock()
    private var recorded: [String: FileProtectionType] = [:]
    private let real = AtomicFileWriter()

    func protection(of name: String) -> FileProtectionType? { lock.withLock { recorded[name] } }

    func write(_ data: Data, to url: URL, protection: FileProtectionType) throws {
        lock.withLock { recorded[url.lastPathComponent] = protection }
        try real.write(data, to: url, protection: protection)
    }
}

final class FileScanJournalProtectionTests: XCTestCase {
    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory.appending(path: "journal-\(UUID().uuidString)")
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
    }

    func testCameraDerivedFilesUseCompleteProtectionAndTheRestUntilFirstUnlock() async throws {
        let recorder = ProtectionRecorder()
        let journal = FileScanJournal(root: root, writer: recorder)
        let scan = try await journal.create(name: "Shop")
        _ = try await journal.saveWorldMap(scanID: scan.scanID, data: Data("map".utf8), snapshotJPEG: Data([0xFF]))
        _ = try await journal.appendRoom(scanID: scan.scanID, capturedRoomJSON: Data("{}".utf8), name: "Room 1")
        XCTAssertEqual(recorder.protection(of: ScanFiles.worldMap), .complete)
        XCTAssertEqual(recorder.protection(of: ScanFiles.relocalizationSnapshot), .complete)
        XCTAssertEqual(recorder.protection(of: ScanFiles.manifest), .completeUntilFirstUserAuthentication)
        XCTAssertEqual(recorder.protection(of: "0.json"), .completeUntilFirstUserAuthentication)
    }

    func testScansFolderIsExcludedFromBackup() async throws {
        let journal = FileScanJournal(root: root)
        _ = try await journal.create(name: "Shop")
        let values = try root.resourceValues(forKeys: [.isExcludedFromBackupKey])
        XCTAssertEqual(values.isExcludedFromBackup, true)
    }

    func testWriterMapsProtectionToWritingOptions() {
        XCTAssertEqual(AtomicFileWriter.writingOptions(for: .complete), .completeFileProtection)
        XCTAssertEqual(AtomicFileWriter.writingOptions(for: .completeUntilFirstUserAuthentication), .completeFileProtectionUntilFirstUserAuthentication)
    }

    func testReleasingHeavyFilesKeepsRoomsAndManifest() async throws {
        let journal = FileScanJournal(root: root)
        let scan = try await journal.create(name: "Shop")
        _ = try await journal.appendRoom(scanID: scan.scanID, capturedRoomJSON: Data("{}".utf8), name: "Room 1")
        _ = try await journal.saveWorldMap(scanID: scan.scanID, data: Data("map".utf8), snapshotJPEG: Data([0xFF]))
        _ = try await journal.saveMesh(scanID: scan.scanID, data: Data([1, 2, 3]))

        try await journal.releaseHeavyFiles(scanID: scan.scanID)
        let directory = journal.directory(for: scan.scanID)
        for file in ScanFiles.heavy {
            XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appending(path: file).path), file)
        }
        let stored = try await journal.load(scanID: scan.scanID)
        XCTAssertNil(stored.meshFile)
        XCTAssertNil(stored.worldMapFile)
        XCTAssertNil(stored.relocalizationSnapshotFile)
        XCTAssertEqual(stored.rooms.count, 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appending(path: ScanFiles.room(0)).path))
    }
}

final class FileScanJournalTests: XCTestCase {
    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory.appending(path: "journal-\(UUID().uuidString)")
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
    }

    private func roomJSON(_ index: Int) -> Data {
        Data("{\"identifier\":\"room-\(index)\",\"walls\":[]}".utf8)
    }

    func testCreateWritesManifestAndRoomsFolder() async throws {
        let journal = FileScanJournal(root: root)
        let manifest = try await journal.create(name: "Corner cafe")
        let directory = journal.directory(for: manifest.scanID)
        XCTAssertEqual(directory, root.appending(path: manifest.scanID.uuidString, directoryHint: .isDirectory))
        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appending(path: "manifest.json").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appending(path: "rooms").path))
        let loaded = try await journal.load(scanID: manifest.scanID)
        XCTAssertEqual(loaded, manifest)
    }

    func testRoomsWorldMapAndMeshRoundTrip() async throws {
        let journal = FileScanJournal(root: root)
        var manifest = try await journal.create(name: "Shop")
        manifest.phase = .scanning(room: 0)
        try await journal.update(manifest)
        _ = try await journal.appendRoom(scanID: manifest.scanID, capturedRoomJSON: roomJSON(0), name: "Front")
        _ = try await journal.appendRoom(scanID: manifest.scanID, capturedRoomJSON: roomJSON(1), name: "Back")
        _ = try await journal.saveWorldMap(scanID: manifest.scanID, data: Data([1, 2, 3]), snapshotJPEG: Data([0xFF, 0xD8]))
        let saved = try await journal.saveMesh(scanID: manifest.scanID, data: Data("SPM1".utf8))

        let reloaded = try await FileScanJournal(root: root).load(scanID: manifest.scanID)
        XCTAssertEqual(reloaded, saved)
        XCTAssertEqual(reloaded.rooms.map(\.name), ["Front", "Back"])
        XCTAssertEqual(reloaded.rooms.map(\.capturedRoomFile), ["rooms/0.json", "rooms/1.json"])
        XCTAssertEqual(reloaded.worldMapFile, "worldmap.arworldmap")
        XCTAssertEqual(reloaded.relocalizationSnapshotFile, "relocalize.jpg")
        XCTAssertEqual(reloaded.meshFile, "mesh.spm")
        XCTAssertNotNil(reloaded.worldMapSavedAt)
        let directory = journal.directory(for: manifest.scanID)
        XCTAssertEqual(try Data(contentsOf: directory.appending(path: "rooms/1.json")), roomJSON(1))
        XCTAssertEqual(try Data(contentsOf: directory.appending(path: "worldmap.arworldmap")), Data([1, 2, 3]))
    }

    func testUnfinishedScansSkipsFinishedAndEmptyScans() async throws {
        let journal = FileScanJournal(root: root)
        var finished = try await journal.create(name: "Done")
        finished.phase = .finished
        try await journal.update(finished)
        _ = try await journal.create(name: "Never started")
        var paused = try await journal.create(name: "Paused")
        paused.phase = .paused(room: 0, reason: .backgrounded)
        try await journal.update(paused)
        var between = try await journal.create(name: "Between")
        between = try await journal.appendRoom(scanID: between.scanID, capturedRoomJSON: roomJSON(0), name: "A")
        between.phase = .betweenRooms(completed: 1)
        try await journal.update(between)

        let unfinished = try await FileScanJournal(root: root).unfinishedScans()
        XCTAssertEqual(Set(unfinished.map(\.name)), ["Paused", "Between"])
    }

    func testUnfinishedScansIgnoresCorruptAndForeignFolders() async throws {
        let journal = FileScanJournal(root: root)
        var good = try await journal.create(name: "Good")
        good.phase = .scanning(room: 0)
        try await journal.update(good)
        let corrupt = root.appending(path: UUID().uuidString)
        try FileManager.default.createDirectory(at: corrupt, withIntermediateDirectories: true)
        try Data("{not json".utf8).write(to: corrupt.appending(path: "manifest.json"))
        try FileManager.default.createDirectory(at: root.appending(path: "not-a-scan"), withIntermediateDirectories: true)

        let unfinished = try await journal.unfinishedScans()
        XCTAssertEqual(unfinished.map(\.scanID), [good.scanID])
    }

    func testUnfinishedScansOnMissingRootIsEmpty() async throws {
        let unfinished = try await FileScanJournal(root: root).unfinishedScans()
        XCTAssertEqual(unfinished, [])
    }

    func testRejectsManifestFromNewerVersion() async throws {
        let journal = FileScanJournal(root: root)
        var manifest = try await journal.create(name: "Future")
        manifest.version = ScanManifest.currentVersion + 1
        try await journal.update(manifest)
        do {
            _ = try await journal.load(scanID: manifest.scanID)
            XCTFail("expected unsupportedVersion")
        } catch {
            XCTAssertEqual(error as? ScanJournalError, .unsupportedVersion(ScanManifest.currentVersion + 1))
        }
    }

    func testOrphanRoomFromKillBeforeManifestIsAdopted() async throws {
        let journal = FileScanJournal(root: root)
        var manifest = try await journal.create(name: "Shop")
        manifest.phase = .scanning(room: 0)
        try await journal.update(manifest)
        let directory = journal.directory(for: manifest.scanID)
        try AtomicFileWriter().write(roomJSON(0), to: directory.appending(path: "rooms/0.json"))

        let recovered = try await FileScanJournal(root: root).load(scanID: manifest.scanID)
        XCTAssertEqual(recovered.rooms.count, 1)
        XCTAssertEqual(recovered.rooms.first?.name, "Room 1")
        XCTAssertEqual(recovered.phase, .betweenRooms(completed: 1))
        let again = try await FileScanJournal(root: root).load(scanID: manifest.scanID)
        XCTAssertEqual(again, recovered)
    }

    func testPartialOrphanRoomIsNotAdopted() async throws {
        let journal = FileScanJournal(root: root)
        let manifest = try await journal.create(name: "Shop")
        let directory = journal.directory(for: manifest.scanID)
        try Data("{\"walls\":[".utf8).write(to: directory.appending(path: "rooms/0.json"))
        let loaded = try await journal.load(scanID: manifest.scanID)
        XCTAssertEqual(loaded.rooms, [])
    }

    func testCarryOverMeshKeepsLatestMeshAsBase() async throws {
        let journal = FileScanJournal(root: root)
        let manifest = try await journal.create(name: "Shop")
        try await journal.carryOverMesh(scanID: manifest.scanID)
        let none = await journal.carriedOverMesh(scanID: manifest.scanID)
        XCTAssertNil(none)
        _ = try await journal.saveMesh(scanID: manifest.scanID, data: Data([7]))
        try await journal.carryOverMesh(scanID: manifest.scanID)
        let base = await journal.carriedOverMesh(scanID: manifest.scanID)
        XCTAssertEqual(base, Data([7]))
    }

    func testDeleteRemovesScan() async throws {
        let journal = FileScanJournal(root: root)
        let manifest = try await journal.create(name: "Shop")
        try await journal.delete(scanID: manifest.scanID)
        XCTAssertFalse(FileManager.default.fileExists(atPath: journal.directory(for: manifest.scanID).path))
        try await journal.delete(scanID: manifest.scanID)
    }

    // MARK: Crash at every write

    private struct Recorder {
        var scanID: UUID?
        var committed: [ScanManifest] = []
    }

    /// Every journal operation a real walk performs, in order. Returns after the first failure.
    private func walk(_ journal: FileScanJournal, recorder: inout Recorder) async {
        do {
            var manifest = try await journal.create(name: "Walk")
            recorder.scanID = manifest.scanID
            recorder.committed.append(manifest)
            manifest.phase = .scanning(room: 0)
            try await journal.update(manifest)
            recorder.committed.append(manifest)
            recorder.committed.append(try await journal.saveWorldMap(scanID: manifest.scanID, data: Data(repeating: 1, count: 4096), snapshotJPEG: Data(repeating: 2, count: 512)))
            manifest = try await journal.appendRoom(scanID: manifest.scanID, capturedRoomJSON: roomJSON(0), name: "Front")
            recorder.committed.append(manifest)
            manifest.phase = .scanning(room: 1)
            try await journal.update(manifest)
            recorder.committed.append(manifest)
            recorder.committed.append(try await journal.saveWorldMap(scanID: manifest.scanID, data: Data(repeating: 3, count: 4096), snapshotJPEG: nil))
            manifest = try await journal.appendRoom(scanID: manifest.scanID, capturedRoomJSON: roomJSON(1), name: "Back")
            recorder.committed.append(manifest)
            manifest = try await journal.saveMesh(scanID: manifest.scanID, data: Data(repeating: 4, count: 2048))
            recorder.committed.append(manifest)
        } catch {
            return
        }
    }

    func testSurvivesKillAtEveryWrite() async throws {
        let counter = CountingWriter()
        var reference = Recorder()
        await walk(FileScanJournal(root: root, writer: counter), recorder: &reference)
        let totalWrites = counter.count
        XCTAssertEqual(reference.committed.count, 8)
        XCTAssertGreaterThan(totalWrites, 8)

        for crashPoint in 0..<totalWrites {
            try? FileManager.default.removeItem(at: root)
            var recorder = Recorder()
            await walk(FileScanJournal(root: root, writer: CrashingWriter(survivingWrites: crashPoint)), recorder: &recorder)
            try await assertRecoverable(recorder, crashPoint: crashPoint)
        }
    }

    private func assertRecoverable(_ recorder: Recorder, crashPoint: Int) async throws {
        let relaunched = FileScanJournal(root: root)
        guard let scanID = recorder.scanID else {
            let unfinished = try await relaunched.unfinishedScans()
            XCTAssertEqual(unfinished, [], "crash \(crashPoint)")
            return
        }
        let loaded = try await relaunched.load(scanID: scanID)
        let last = try XCTUnwrap(recorder.committed.last, "crash \(crashPoint)")
        XCTAssertTrue(loaded == last || loaded.rooms.count == last.rooms.count + 1, "crash \(crashPoint): \(loaded)")
        XCTAssertEqual(loaded.version, ScanManifest.currentVersion)

        let directory = relaunched.directory(for: scanID)
        for room in loaded.rooms {
            let data = try Data(contentsOf: directory.appending(path: room.capturedRoomFile))
            XCTAssertNotNil(try? JSONSerialization.jsonObject(with: data), "crash \(crashPoint)")
        }
        if let worldMap = loaded.worldMapFile {
            XCTAssertEqual(try Data(contentsOf: directory.appending(path: worldMap)).count, 4096, "crash \(crashPoint)")
        }
        try assertNoTemporaryFiles(in: directory, crashPoint: crashPoint)

        let continued = try await relaunched.appendRoom(scanID: scanID, capturedRoomJSON: roomJSON(9), name: "After")
        XCTAssertEqual(continued.rooms.count, loaded.rooms.count + 1, "crash \(crashPoint)")
    }

    private func assertNoTemporaryFiles(in directory: URL, crashPoint: Int) throws {
        let enumerator = FileManager.default.enumerator(at: directory, includingPropertiesForKeys: nil)
        let leftovers = (enumerator?.allObjects as? [URL] ?? []).filter(AtomicFileWriter.isTemporaryFile)
        XCTAssertEqual(leftovers, [], "crash \(crashPoint)")
    }
}
