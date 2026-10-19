import simd
import SwiftUI
import XCTest
@testable import StandardPhysics

@MainActor
final class CaptureCoordinatorTests: XCTestCase {
    private var root: URL!
    private var host: FakeARHost!
    private var scanner: FakeRoomScanner!
    private var merger: FakeMerger!
    private var application: FakeApplication!
    private var notifications: NotificationCenter!
    private var thermal = ProcessInfo.ThermalState.nominal
    private var relocalizationTimeout = Duration.seconds(3600)

    override func setUp() async throws {
        root = FileManager.default.temporaryDirectory.appending(path: "capture-\(UUID().uuidString)")
        notifications = NotificationCenter()
        relaunchDevices()
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: root)
    }

    /// New fakes, same disk: what the app sees after being killed and relaunched.
    private func relaunchDevices() {
        host = FakeARHost()
        scanner = FakeRoomScanner()
        merger = FakeMerger()
        application = FakeApplication()
    }

    private func makeCoordinator() -> CaptureCoordinator {
        var dependencies = CaptureDependencies(
            journal: FileScanJournal(root: root),
            host: host,
            scanner: scanner,
            merger: merger,
            application: application
        )
        dependencies.notificationCenter = notifications
        dependencies.thermalState = { [unowned self] in thermal }
        dependencies.relocalizationTimeout = relocalizationTimeout
        dependencies.sleep = { duration in
            if duration < .seconds(60) { return }
            try await Task.sleep(for: .seconds(3600))
        }
        return CaptureCoordinator(dependencies: dependencies)
    }

    private func eventually(_ description: String, _ condition: () -> Bool) async {
        for _ in 0..<400 where !condition() {
            try? await Task.sleep(for: .milliseconds(5))
        }
        XCTAssertTrue(condition(), description)
    }

    private func storedManifest(_ coordinator: CaptureCoordinator) async throws -> ScanManifest {
        try await FileScanJournal(root: root).load(scanID: XCTUnwrap(coordinator.manifest?.scanID))
    }

    // MARK: Start

    func testStartScanRunsFreshSessionAndKeepsScreenAwake() async throws {
        let coordinator = makeCoordinator()
        await coordinator.startScan(name: "Corner cafe")
        XCTAssertEqual(coordinator.phase, .scanning(room: 0))
        XCTAssertEqual(host.runModes, [.fresh])
        XCTAssertEqual(scanner.starts, 1)
        XCTAssertTrue(application.isIdleTimerDisabled)
        let stored = try await storedManifest(coordinator)
        XCTAssertEqual(stored.phase, .scanning(room: 0))
        XCTAssertEqual(stored.name, "Corner cafe")
    }

    // MARK: Interruptions pause, never finish

    func testScenePhasesPauseAndResumeWithoutEndingTheRoom() async throws {
        let coordinator = makeCoordinator()
        await coordinator.startScan(name: "Shop")
        coordinator.handleScenePhase(.inactive)
        coordinator.handleScenePhase(.background)
        await coordinator.settle()
        XCTAssertEqual(coordinator.phase, .paused(room: 0, reason: .backgrounded))
        XCTAssertEqual(host.pauses, 1)
        let stored = try await storedManifest(coordinator)
        XCTAssertEqual(stored.phase, .paused(room: 0, reason: .backgrounded))

        coordinator.handleScenePhase(.inactive)
        coordinator.handleScenePhase(.active)
        await coordinator.settle()
        XCTAssertEqual(coordinator.phase, .scanning(room: 0))
        XCTAssertEqual(host.runModes, [.fresh, .continueExisting])
        XCTAssertEqual(scanner.finishes, 0)
        XCTAssertEqual(scanner.cancels, 0)
        XCTAssertTrue(application.isIdleTimerDisabled)
    }

    func testSessionInterruptionPausesThenRelocalizes() async {
        let coordinator = makeCoordinator()
        await coordinator.startScan(name: "Shop")
        host.emit(.interrupted)
        await eventually("paused") { coordinator.phase == .paused(room: 0, reason: .sessionInterrupted) }
        host.emit(.interruptionEnded)
        host.emit(.tracking(.limited(.relocalizing)))
        await eventually("relocalizing") { coordinator.phase == .relocalizing(room: 0) }
        XCTAssertNotNil(coordinator.guidance)
        host.emit(.tracking(.normal))
        await eventually("scanning") { coordinator.phase == .scanning(room: 0) }
        XCTAssertEqual(scanner.starts, 1)
    }

    func testWillResignActiveSavesCheckpointUnderBackgroundTask() async throws {
        let coordinator = makeCoordinator()
        await coordinator.startScan(name: "Shop")
        notifications.post(name: UIApplication.willResignActiveNotification, object: nil)
        await coordinator.settle()
        XCTAssertEqual(application.protectedWork, 1)
        XCTAssertEqual(application.endedWork, 1)
        let stored = try await storedManifest(coordinator)
        XCTAssertEqual(stored.worldMapFile, "worldmap.arworldmap")
        XCTAssertEqual(coordinator.relocalizationSnapshot, Data([0xFF, 0xD8, 0xFF]))
    }

    func testThermalNotificationPausesWhenCritical() async {
        let coordinator = makeCoordinator()
        await coordinator.startScan(name: "Shop")
        thermal = .critical
        notifications.post(name: ProcessInfo.thermalStateDidChangeNotification, object: nil)
        await coordinator.settle()
        XCTAssertEqual(coordinator.phase, .paused(room: 0, reason: .thermal))
        XCTAssertEqual(host.pauses, 1)
        thermal = .fair
        notifications.post(name: ProcessInfo.thermalStateDidChangeNotification, object: nil)
        await coordinator.settle()
        XCTAssertEqual(coordinator.phase, .scanning(room: 0))
    }

    // MARK: Rooms

    func testFinishRoomSavesRoomMeshAndFindings() async throws {
        let coordinator = makeCoordinator()
        let finding = Finding(ruleID: "r1", jurisdiction: .ada2010, section: "404", subjectID: "door", status: .fail, measured: nil, required: ">= 32 in", message: "Too narrow")
        coordinator.onRoomFinished = { _ in [finding] }
        host.parts = [MeshPart(id: UUID(), transform: matrix_identity_float4x4, vertices: Data(count: 36), indices: Data(count: 12), classification: nil)]
        await coordinator.startScan(name: "Shop")
        await coordinator.finishRoom()

        XCTAssertEqual(coordinator.phase, .betweenRooms(completed: 1))
        XCTAssertTrue(coordinator.canStartNextRoom)
        let stored = try await storedManifest(coordinator)
        XCTAssertEqual(stored.rooms.map(\.capturedRoomFile), ["rooms/0.json"])
        XCTAssertEqual(stored.meshFile, "mesh.spm")
        XCTAssertEqual(stored.worldMapFile, "worldmap.arworldmap")
        XCTAssertEqual(stored.phase, .betweenRooms(completed: 1))
        await eventually("findings") { coordinator.provisionalFindings == [finding] }

        await coordinator.nameRoom(index: 0, name: "Sales floor")
        let renamed = try await storedManifest(coordinator)
        XCTAssertEqual(renamed.rooms.first?.name, "Sales floor")

        coordinator.startNextRoom()
        await coordinator.settle()
        XCTAssertEqual(coordinator.phase, .scanning(room: 1))
        XCTAssertEqual(scanner.starts, 2)
        XCTAssertEqual(host.runModes, [.fresh])
    }

    func testRestartRoomRescansInPlace() async {
        let coordinator = makeCoordinator()
        await coordinator.startScan(name: "Shop")
        coordinator.restartRoom()
        await coordinator.settle()
        XCTAssertEqual(scanner.cancels, 1)
        XCTAssertEqual(scanner.starts, 2)
        XCTAssertEqual(coordinator.phase, .scanning(room: 0))
    }

    func testGuidanceFollowsRoomPlanInstructions() async {
        let coordinator = makeCoordinator()
        await coordinator.startScan(name: "Shop")
        scanner.emit(.instruction(.slowDown))
        await eventually("guidance") { coordinator.guidance == "Slow down" }
        scanner.emit(.instruction(.normal))
        await eventually("cleared") { coordinator.guidance == nil }
    }

    // MARK: Finishing

    func testFinishScanSavesLastRoomAndExportsStructure() async throws {
        let coordinator = makeCoordinator()
        await coordinator.startScan(name: "Shop")
        await coordinator.finishRoom()
        coordinator.startNextRoom()
        await coordinator.finishScan()

        XCTAssertEqual(coordinator.phase, .finished)
        XCTAssertEqual(merger.lastCall?.files, ["rooms/0.json", "rooms/1.json"])
        XCTAssertEqual(merger.lastCall?.frames, [0, 0])
        XCTAssertEqual(coordinator.exportedStructures.first?.usdzFile, "structure.usdz")
        XCTAssertFalse(application.isIdleTimerDisabled)
        let stored = try await storedManifest(coordinator)
        XCTAssertEqual(stored.phase, .finished)
        let unfinished = try await FileScanJournal(root: root).unfinishedScans()
        XCTAssertEqual(unfinished, [])
    }

    func testExportFailureFailsTheScanButKeepsItResumable() async throws {
        merger.error = CocoaError(.fileWriteOutOfSpace)
        let coordinator = makeCoordinator()
        await coordinator.startScan(name: "Shop")
        await coordinator.finishScan()
        guard case .failed = coordinator.phase else { return XCTFail("expected failure, got \(coordinator.phase)") }
        let unfinished = try await FileScanJournal(root: root).unfinishedScans()
        XCTAssertEqual(unfinished.count, 1)
    }

    func testDiscardDeletesEverything() async throws {
        let coordinator = makeCoordinator()
        await coordinator.startScan(name: "Shop")
        let scanID = try XCTUnwrap(coordinator.manifest?.scanID)
        await coordinator.discardScan()
        XCTAssertEqual(coordinator.phase, .idle)
        XCTAssertNil(coordinator.manifest)
        XCTAssertFalse(application.isIdleTimerDisabled)
        XCTAssertFalse(FileManager.default.fileExists(atPath: root.appending(path: scanID.uuidString).path))
    }

    // MARK: Kill, relaunch, relocalize, continue

    func testKillRelaunchRelocalizesAndContinuesTheInterruptedRoom() async throws {
        var first: CaptureCoordinator? = makeCoordinator()
        await first?.startScan(name: "Shop")
        await first?.finishRoom()
        first?.startNextRoom()
        host.emit(.checkpointDue)
        await eventually("checkpoint") { self.host.runs.count == 1 }
        await first?.settle()
        let scanID = try XCTUnwrap(first?.manifest?.scanID)
        first = nil

        relaunchDevices()
        let unfinished = try await FileScanJournal(root: root).unfinishedScans()
        XCTAssertEqual(unfinished.map(\.scanID), [scanID])
        XCTAssertEqual(unfinished.first?.phase, .scanning(room: 1))

        let second = makeCoordinator()
        await second.resume(scanID: scanID)
        XCTAssertEqual(second.phase, .relocalizing(room: 1))
        XCTAssertEqual(host.runModes, [.relocalize])
        XCTAssertEqual(host.runs.first?.worldMap, Data("map".utf8))
        XCTAssertEqual(second.relocalizationSnapshot, Data([0xFF, 0xD8, 0xFF]))
        XCTAssertTrue(application.isIdleTimerDisabled)
        XCTAssertEqual(scanner.starts, 0)

        host.emit(.tracking(.limited(.relocalizing)))
        host.emit(.tracking(.normal))
        await eventually("continued") { second.phase == .scanning(room: 1) }
        await second.settle()
        XCTAssertEqual(scanner.starts, 1)

        await second.finishScan()
        XCTAssertEqual(second.phase, .finished)
        XCTAssertEqual(merger.lastCall?.frames, [0, 0], "relocalized rooms share the original frame")
    }

    func testRelocalizationTimeoutOffersRestartInNewFrame() async throws {
        let first = makeCoordinator()
        await first.startScan(name: "Shop")
        await first.finishRoom()
        first.startNextRoom()
        await first.settle()
        let scanID = try XCTUnwrap(first.manifest?.scanID)

        relaunchDevices()
        relocalizationTimeout = .seconds(1)
        let second = makeCoordinator()
        await second.resume(scanID: scanID)
        await eventually("timed out") { second.relocalizationTimedOut }
        XCTAssertEqual(second.phase, .relocalizing(room: 1))
        XCTAssertNotNil(second.guidance)

        second.restartRoom()
        await second.settle()
        XCTAssertEqual(second.phase, .scanning(room: 1))
        XCTAssertEqual(host.runModes, [.relocalize, .fresh])
        XCTAssertEqual(scanner.starts, 1)
        await second.finishScan()
        XCTAssertEqual(merger.lastCall?.frames, [0, 1], "a restarted room lives in a new frame")
    }

    func testUnreadableWorldMapFallsBackToRestartingTheRoom() async throws {
        let first = makeCoordinator()
        await first.startScan(name: "Shop")
        host.emit(.checkpointDue)
        await eventually("checkpointed") { first.manifest?.worldMapFile != nil }
        let scanID = try XCTUnwrap(first.manifest?.scanID)

        relaunchDevices()
        host.runError = ARSessionHostError.unreadableWorldMap
        let second = makeCoordinator()
        await second.resume(scanID: scanID)
        await second.settle()
        XCTAssertEqual(host.runModes, [.relocalize, .fresh])
        XCTAssertEqual(second.phase, .failed(message: "The camera couldn't start."))
    }

    func testRelaunchBetweenRoomsWaitsForNextRoomToRelocalize() async throws {
        let first = makeCoordinator()
        await first.startScan(name: "Shop")
        await first.finishRoom()
        let scanID = try XCTUnwrap(first.manifest?.scanID)

        relaunchDevices()
        let second = makeCoordinator()
        await second.resume(scanID: scanID)
        XCTAssertEqual(second.phase, .betweenRooms(completed: 1))
        XCTAssertEqual(host.runModes, [])
        second.startNextRoom()
        await second.settle()
        XCTAssertEqual(second.phase, .relocalizing(room: 1))
        XCTAssertEqual(host.runModes, [.relocalize])
    }
}
