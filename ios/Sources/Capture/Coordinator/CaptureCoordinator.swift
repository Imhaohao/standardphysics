import ARKit
import Foundation
import Observation
import os
import RoomPlan
import SwiftUI
import UIKit

/// Runs the capture flow: feeds every outside signal into `CaptureStateMachine` and performs the
/// effects it returns, one at a time, in order.
@Observable
final class CaptureCoordinator: CaptureControlling {
    private(set) var phase: CapturePhase = .idle
    private(set) var manifest: ScanManifest?
    private(set) var finishedRoomElements: [LiveElement] = []
    private(set) var currentRoomElements: [LiveElement] = []
    /// Every mesh piece seen this scan, by anchor. RoomPlan removes the session's mesh anchors when it
    /// gives up on a room, so the mesh is collected at each checkpoint instead of only at the end.
    private var meshLibrary: [UUID: MeshPart] = [:]
    /// Confirmed detector objects: those kept with finished rooms plus the room in progress.
    private(set) var detections: [Detection] = []
    @ObservationIgnored private var finishedRoomDetections: [Detection] = []
    @ObservationIgnored private var detectionAccumulator = DetectionAccumulator()
    private var onDeviceFindings: [Finding] = []
    private var serverFindings: [Finding] = []
    private(set) var guidance: String?
    private(set) var relocalizationSnapshot: Data?
    private(set) var relocalizationTimedOut = false
    private(set) var canStartNextRoom = false
    private(set) var exportedStructures: [ExportedStructure] = []

    /// Plug the on-device engine in here, e.g. `coordinator.onRoomFinished = engine.evaluateRoom`.
    /// Told about each milestone once it is on disk, e.g. to stream the scan to the server.
    @ObservationIgnored weak var observer: (any CaptureObserving)?

    @ObservationIgnored var onRoomFinished: (@Sendable (_ capturedRoomJSON: Data, _ detectedObjects: [DetectedObject]) async throws -> [Finding])?

    /// Photo crops of the finished room's doubtful RoomPlan objects, for the server to relabel.
    @ObservationIgnored var makeRelabelCrops: (@Sendable (_ capturedRoomJSON: Data) async -> [RelabelCrop])?

    var liveElements: [LiveElement] { finishedRoomElements + currentRoomElements }
    var provisionalFindings: [Finding] {
        FindingMerge.preferringServer(onDevice: onDeviceFindings, server: serverFindings)
    }
    var arSession: ARSession? { dependencies.host.arSession }

    @ObservationIgnored private let dependencies: CaptureDependencies
    @ObservationIgnored private var state = CaptureState()
    @ObservationIgnored private var instruction = ScanInstruction.normal
    @ObservationIgnored private var frameLog = FrameLog()
    @ObservationIgnored private var hasRunSessionThisLaunch = false
    @ObservationIgnored private var effectChain: Task<Void, Never>?
    @ObservationIgnored private var relocalizationTimer: Task<Void, Never>?
    @ObservationIgnored private var listeners: [Task<Void, Never>] = []
    @ObservationIgnored private var observers: [any NSObjectProtocol] = []
    @ObservationIgnored private var stateWaiters: [StateWaiter] = []
    @ObservationIgnored private let logger = Logger(subsystem: "com.tarunyadgirkar.standardphysics", category: "capture")

    init(dependencies: CaptureDependencies) {
        self.dependencies = dependencies
        listen()
    }

    convenience init() {
        self.init(dependencies: .live())
    }

    // MARK: CaptureControlling

    func startScan(name: String) async {
        guard state.activity == .idle else { return }
        do {
            manifest = try await dependencies.journal.create(name: name)
        } catch {
            phase = .failed(message: "Couldn't create a place to save this scan.")
            return
        }
        frameLog = FrameLog()
        resetLiveState()
        if let manifest { notify(.started(manifest)) }
        send(.start)
        send(.thermal(ThermalLevel(dependencies.thermalState())))
        await settle()
    }

    func resume(scanID: UUID) async {
        guard state.activity == .idle else { return }
        do {
            try await restore(scanID: scanID)
        } catch {
            phase = .failed(message: "Couldn't open the saved scan.")
            return
        }
        guard let manifest else { return }
        notify(.resumed(manifest))
        send(.resume(ResumePoint(
            completedRooms: manifest.rooms.count,
            hasWorldMap: manifest.worldMapFile != nil,
            wasBetweenRooms: Self.wasBetweenRooms(manifest.phase)
        )))
        send(.thermal(ThermalLevel(dependencies.thermalState())))
        await settle()
    }

    func pause() { send(.userPause) }
    func continueScanning() { send(.userContinue) }
    func startNextRoom() { send(.nextRoom) }
    func restartRoom() { send(.restartRoom) }

    func finishRoom() async {
        send(.finishRoom)
        await waitUntil { !Self.isSavingRoom($0) }
        await settle()
    }

    func nameRoom(index: Int, name: String) async {
        guard var updated = manifest, updated.rooms.indices.contains(index) else { return }
        updated.rooms[index].name = name
        manifest = updated
        await save(updated)
    }

    func finishScan() async {
        send(.finishScan)
        await waitUntil { !Self.isSavingRoom($0) && $0.activity != .finishing }
        await settle()
    }

    func discardScan() async {
        send(.discard)
        await settle()
    }

    /// The scan held open goes through the state machine's discard, so its `.deleteScan` effect
    /// also stops the session; any other scan only has files on disk to remove.
    func deleteScan(scanID: UUID) async {
        if manifest?.scanID == scanID, state.activity != .idle {
            await discardScan()
            return
        }
        if manifest?.scanID == scanID { manifest = nil }
        do {
            try await dependencies.journal.delete(scanID: scanID)
        } catch {
            logger.error("Delete failed: \(error.localizedDescription)")
        }
        notify(.discarded(scanID: scanID))
    }

    /// Feeds one batch of world-lifted detections to the room in progress.
    func ingest(_ batch: [Detection]) {
        guard case .scanning = phase else { return }
        detectionAccumulator = detectionAccumulator.adding(batch)
        publishDetections()
    }

    private func publishDetections() {
        let current = detectionAccumulator.confirmed.map(\.asDetection)
        let next = finishedRoomDetections + current
        if next != detections { detections = next }
    }

    private func resetRoomDetections() {
        detectionAccumulator = DetectionAccumulator(configuration: detectionAccumulator.configuration)
        publishDetections()
    }

    func handleScenePhase(_ scenePhase: ScenePhase) {
        switch scenePhase {
        case .active: send(.appActivity(.active))
        case .inactive: send(.appActivity(.inactive))
        case .background: send(.appActivity(.background))
        @unknown default: send(.appActivity(.inactive))
        }
    }

    /// Waits until every queued effect has run. Effects can enqueue more, so loop until quiet.
    func settle() async {
        while let chain = effectChain {
            await chain.value
            if effectChain == chain { return }
        }
    }

    // MARK: Events

    func send(_ event: CaptureEvent) {
        let (next, effects) = CaptureStateMachine.reduce(state, event)
        state = next
        publish()
        guard !effects.isEmpty else { return }
        let previous = effectChain
        effectChain = Task { [weak self] in
            await previous?.value
            for effect in effects {
                await self?.perform(effect)
            }
        }
    }

    private func publish() {
        phase = state.phase
        canStartNextRoom = state.canStartNextRoom
        relocalizationTimedOut = state.relocalizationTimedOut
        guidance = GuidanceText.message(for: GuidanceInput(
            phase: state.phase,
            instruction: instruction,
            isThermalWarning: state.isThermalWarning,
            relocalizationTimedOut: state.relocalizationTimedOut,
            lastRoomCaptureError: state.lastRoomCaptureError,
            hasSalvagedRoom: state.salvagedRoomJSON != nil,
            lastRoomEndedAtSceneLimit: state.lastRoomEndedAtSceneLimit
        ))
        resumeSatisfiedWaiters()
    }

    private func waitUntil(_ condition: @escaping (CaptureState) -> Bool) async {
        guard !condition(state) else { return }
        await withCheckedContinuation { continuation in
            stateWaiters.append(StateWaiter(condition: condition, continuation: continuation))
        }
    }

    private func resumeSatisfiedWaiters() {
        let satisfied = stateWaiters.filter { $0.condition(state) }
        stateWaiters.removeAll { $0.condition(state) }
        satisfied.forEach { $0.continuation.resume() }
    }

    private static func isSavingRoom(_ state: CaptureState) -> Bool {
        if case .savingRoom = state.activity { return true }
        return false
    }

    // MARK: Listening

    private func listen() {
        let hostEvents = dependencies.host.events
        let scanUpdates = dependencies.scanner.updates
        listeners.append(Task { [weak self] in
            for await event in hostEvents { self?.handle(event) }
        })
        listeners.append(Task { [weak self] in
            for await update in scanUpdates { self?.handle(update) }
        })
        observe(ProcessInfo.thermalStateDidChangeNotification) { coordinator in
            coordinator.send(.thermal(ThermalLevel(coordinator.dependencies.thermalState())))
        }
        observe(UIApplication.willResignActiveNotification) { coordinator in
            coordinator.send(.appWillResignActive)
        }
    }

    private func observe(_ name: Notification.Name, perform action: @escaping @Sendable @MainActor (CaptureCoordinator) -> Void) {
        let observer = dependencies.notificationCenter.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                action(self)
            }
        }
        observers.append(observer)
    }

    private func handle(_ event: ARHostEvent) {
        Diagnostics.shared.record("ar_event", note: String(describing: event))
        switch event {
        case .tracking(let status): send(.tracking(status))
        case .interrupted: send(.sessionInterrupted)
        case .interruptionEnded: send(.sessionInterruptionEnded)
        case .checkpointDue: send(.checkpointDue)
        case .failed(let message): send(.sessionFailed(message: message))
        }
    }

    private func handle(_ update: RoomScanUpdate) {
        switch update {
        case .elements(let elements): currentRoomElements = elements
        case .instruction(let next):
            instruction = next
            publish()
        case .ended(let roomJSON):
            Diagnostics.shared.record("room_capture_ended", ["bytes": Double(roomJSON.count)])
            send(.roomCaptureEnded(roomJSON: roomJSON))
        case .salvaged(let roomJSON):
            Diagnostics.shared.record("room_capture_salvaged", ["bytes": Double(roomJSON.count), "score": Double(RoomSalvage.score(roomJSON))])
            send(.roomCaptureSalvaged(roomJSON: roomJSON))
        case .sceneLimitReached:
            Diagnostics.shared.record("room_capture_scene_limit")
            send(.roomCaptureReachedSceneLimit)
        case .failed(let message):
            Diagnostics.shared.record("room_capture_failed", note: message)
            send(.roomCaptureFailed(message: message))
        }
    }

    // MARK: Effects

    private func perform(_ effect: CaptureEffect) async {
        switch effect {
        case .runARSession(let mode): await runSession(mode)
        case .pauseARSession: dependencies.host.pause()
        case .startRoomCapture: startRoomCapture()
        case .finishRoomCapture: dependencies.scanner.finish()
        case .cancelRoomCapture: cancelRoomCapture()
        case .saveCheckpoint: await saveCheckpoint()
        case .persistRoom(let index, let roomJSON): await persistRoom(index: index, roomJSON: roomJSON)
        case .exportMesh: await exportMesh()
        case .exportStructure: await exportStructure()
        case .persistManifest: await persistManifest()
        case .setIdleTimerDisabled(let disabled): dependencies.application.isIdleTimerDisabled = disabled
        case .startRelocalizationTimer: startRelocalizationTimer()
        case .cancelRelocalizationTimer: cancelRelocalizationTimer()
        case .deleteScan: await deleteScan()
        }
    }

    private func runSession(_ mode: ARRunMode) async {
        do {
            let worldMap = mode == .relocalize ? try loadWorldMap() : nil
            updateFrame(for: mode)
            try await dependencies.host.run(mode, worldMap: worldMap)
            hasRunSessionThisLaunch = true
        } catch {
            logger.error("AR run \(String(describing: mode)) failed: \(error.localizedDescription)")
            send(mode == .relocalize ? .restartRoom : .sessionFailed(message: "The camera couldn't start."))
        }
    }

    /// A fresh run, or the first run after a relaunch without a world map, starts a new frame.
    private func updateFrame(for mode: ARRunMode) {
        if mode == .relocalize {
            frameLog.rejoinWorldMapFrame()
            return
        }
        guard mode == .fresh || !hasRunSessionThisLaunch else { return }
        if !(frameLog.roomFrames.isEmpty && frameLog.worldMapFrame == nil) {
            frameLog.beginNewFrame()
        }
    }

    private func startRoomCapture() {
        Diagnostics.shared.record("room_capture_started", ["elements_dropped": Double(currentRoomElements.count)])
        currentRoomElements = []
        resetRoomDetections()
        instruction = .normal
        dependencies.scanner.start()
        recordSessionConfiguration()
        publish()
    }

    /// RoomPlan may swap the shared session's configuration; this shows whether LiDAR meshing survived.
    private func recordSessionConfiguration() {
        let configuration = arSession?.configuration as? ARWorldTrackingConfiguration
        Diagnostics.shared.record("session_configuration", [
            "scene_reconstruction": Double(configuration?.sceneReconstruction.rawValue ?? 0),
            "scene_depth": configuration?.frameSemantics.contains(.sceneDepth) == true ? 1 : 0,
        ], note: configuration.map { String(describing: type(of: $0)) } ?? "none")
    }

    private func cancelRoomCapture() {
        dependencies.scanner.cancel()
        currentRoomElements = []
        resetRoomDetections()
    }

    private func saveCheckpoint() async {
        guard let scanID = manifest?.scanID else { return }
        recordSessionConfiguration()
        collectMesh()
        let token = dependencies.application.beginProtectedWork(named: "Save scan checkpoint")
        defer { dependencies.application.endProtectedWork(token) }
        do {
            guard let checkpoint = try await dependencies.host.checkpoint() else { return }
            adopt(try await dependencies.journal.saveWorldMap(scanID: scanID, data: checkpoint.worldMap, snapshotJPEG: checkpoint.snapshotJPEG))
            relocalizationSnapshot = checkpoint.snapshotJPEG ?? relocalizationSnapshot
            frameLog.worldMapFrame = frameLog.current
            try await dependencies.journal.saveFrameLog(frameLog, scanID: scanID)
        } catch {
            logger.error("Checkpoint failed: \(error.localizedDescription)")
        }
    }

    private func persistRoom(index: Int, roomJSON: Data) async {
        guard let scanID = manifest?.scanID else { return }
        do {
            adopt(try await dependencies.journal.appendRoom(scanID: scanID, capturedRoomJSON: roomJSON, name: "Room \(index + 1)"))
            frameLog.recordRoom(index)
            try await dependencies.journal.saveFrameLog(frameLog, scanID: scanID)
        } catch {
            send(.sessionFailed(message: "Couldn't save the room to this phone."))
            return
        }
        let detectedObjects = await persistDetectedObjects(scanID: scanID, index: index, roomJSON: roomJSON)
        await persistRelabelCrops(scanID: scanID, index: index, roomJSON: roomJSON)
        finishedRoomElements += currentRoomElements
        currentRoomElements = []
        if let manifest { notify(.roomSaved(index: index, manifest: manifest)) }
        evaluate(roomJSON, detectedObjects: detectedObjects)
    }

    /// RoomPlan stays the source of truth: tracks it already reported are dropped here.
    private func persistDetectedObjects(scanID: UUID, index: Int, roomJSON: Data) async -> [DetectedObject] {
        let room = CapturedRoomGeometry(capturedRoomJSON: roomJSON) ?? CapturedRoomGeometry(floorLevel: 0, objects: [])
        let finished = DetectedObjects.finished(tracks: detectionAccumulator.confirmed, room: room)
        finishedRoomDetections += finished.kept.map(\.asDetection)
        resetRoomDetections()
        guard !finished.objects.isEmpty else { return [] }
        do {
            try await dependencies.journal.saveDetectedObjects(finished.objects, scanID: scanID, roomIndex: index)
        } catch {
            logger.error("Detector objects were not saved: \(error.localizedDescription)")
        }
        Diagnostics.shared.record("room_detector_objects", ["count": Double(finished.objects.count)])
        return finished.objects
    }

    /// Saved before the room is announced, so the streamer finds the crops when it sends the room.
    private func persistRelabelCrops(scanID: UUID, index: Int, roomJSON: Data) async {
        guard let makeRelabelCrops else { return }
        let crops = await makeRelabelCrops(roomJSON)
        guard !crops.isEmpty else { return }
        do {
            try await dependencies.journal.saveRelabelCrops(crops, scanID: scanID, roomIndex: index)
        } catch {
            logger.error("Relabel crops were not saved: \(error.localizedDescription)")
        }
        Diagnostics.shared.record("room_relabel_crops", ["count": Double(crops.count)])
    }

    private func evaluate(_ roomJSON: Data, detectedObjects: [DetectedObject]) {
        guard let onRoomFinished else { return }
        Task { [weak self] in
            do {
                let findings = try await onRoomFinished(roomJSON, detectedObjects)
                self?.onDeviceFindings += findings
            } catch {
                self?.logger.error("Room evaluation failed: \(error.localizedDescription)")
            }
        }
    }

    private func exportMesh() async {
        guard let scanID = manifest?.scanID else { return }
        collectMesh()
        let parts = Array(meshLibrary.values)
        Diagnostics.shared.record("mesh_export", [
            "parts": Double(parts.count),
            "vertices": Double(parts.reduce(0) { $0 + $1.vertices.count / MeshPart.bytesPerVertex }),
        ])
        let carriedOver = await dependencies.journal.carriedOverMesh(scanID: scanID)
        let data = await MeshExporter.encode(parts, carriedOver: carriedOver)
        do {
            adopt(try await dependencies.journal.saveMesh(scanID: scanID, data: data))
            if let manifest { notify(.meshSaved(manifest)) }
        } catch {
            logger.error("Mesh export failed: \(error.localizedDescription)")
        }
    }

    private func exportStructure() async {
        guard let manifest else { return }
        do {
            exportedStructures = try await dependencies.merger.export(
                scanDirectory: dependencies.journal.directory(for: manifest.scanID),
                roomFiles: manifest.rooms.map(\.capturedRoomFile),
                frames: manifest.rooms.indices.map(frameLog.frame(ofRoom:))
            )
            send(.exportFinished)
        } catch {
            send(.exportFailed(message: "Couldn't put the rooms together: \(error.localizedDescription)"))
        }
    }

    private func persistManifest() async {
        guard var current = manifest else { return }
        current.phase = state.phase
        manifest = current
        await save(current)
    }

    private func save(_ manifest: ScanManifest) async {
        do {
            try await dependencies.journal.update(manifest)
        } catch {
            logger.error("Manifest save failed: \(error.localizedDescription)")
        }
    }

    private func deleteScan() async {
        if let scanID = manifest?.scanID {
            do {
                try await dependencies.journal.delete(scanID: scanID)
            } catch {
                logger.error("Delete failed: \(error.localizedDescription)")
            }
            notify(.discarded(scanID: scanID))
        }
        manifest = nil
        resetLiveState()
    }

    private func startRelocalizationTimer() {
        relocalizationTimer?.cancel()
        let sleep = dependencies.sleep
        let timeout = dependencies.relocalizationTimeout
        relocalizationTimer = Task { [weak self] in
            do {
                try await sleep(timeout)
            } catch {
                return
            }
            self?.send(.relocalizationTimedOut)
        }
    }

    private func cancelRelocalizationTimer() {
        relocalizationTimer?.cancel()
        relocalizationTimer = nil
    }

    // MARK: Restoring

    private func restore(scanID: UUID) async throws {
        let journal = dependencies.journal
        let loaded = try await journal.load(scanID: scanID)
        try await journal.carryOverMesh(scanID: scanID)
        frameLog = await journal.frameLog(scanID: scanID)
        manifest = loaded
        resetLiveState()
        let directory = journal.directory(for: scanID)
        relocalizationSnapshot = loaded.relocalizationSnapshotFile.flatMap { try? Data(contentsOf: directory.appending(path: $0)) }
        finishedRoomElements = await Self.elements(of: loaded.rooms, in: directory)
    }

    @concurrent
    private static func elements(of rooms: [RoomRecord], in directory: URL) async -> [LiveElement] {
        let decoder = JSONDecoder()
        return rooms.flatMap { record -> [LiveElement] in
            guard let data = try? Data(contentsOf: directory.appending(path: record.capturedRoomFile)),
                  let room = try? decoder.decode(CapturedRoom.self, from: data) else { return [] }
            return LiveElementMapper.elements(of: room)
        }
    }

    private func loadWorldMap() throws -> Data {
        guard let manifest, let file = manifest.worldMapFile else { throw ARSessionHostError.missingWorldMap }
        return try Data(contentsOf: dependencies.journal.directory(for: manifest.scanID).appending(path: file))
    }

    private static func wasBetweenRooms(_ phase: CapturePhase) -> Bool {
        switch phase {
        case .betweenRooms, .finishing, .finished, .failed: true
        case .idle, .scanning, .paused, .relocalizing: false
        }
    }

    /// The journal returns what is on disk; the phase and the server id in memory may be ahead of it.
    private func adopt(_ saved: ScanManifest) {
        var current = saved
        current.phase = state.phase
        current.remoteScanID = manifest?.remoteScanID ?? saved.remoteScanID
        current.remoteCreateKey = manifest?.remoteCreateKey ?? saved.remoteCreateKey
        manifest = current
    }

    private func notify(_ milestone: CaptureMilestone) {
        observer?.capture(self, reached: milestone)
    }

    private func collectMesh() {
        for part in dependencies.host.meshParts() {
            meshLibrary[part.id] = part
        }
    }

    private func resetLiveState() {
        meshLibrary = [:]
        finishedRoomElements = []
        currentRoomElements = []
        finishedRoomDetections = []
        resetRoomDetections()
        onDeviceFindings = []
        serverFindings = []
        exportedStructures = []
        relocalizationSnapshot = nil
        instruction = .normal
    }
}

extension CaptureCoordinator: CaptureLinking {
    func recordRemoteCreateKey(_ key: String, forScan scanID: UUID) async {
        guard var updated = manifest, updated.scanID == scanID, updated.remoteCreateKey == nil else { return }
        updated.remoteCreateKey = key
        manifest = updated
        await save(updated)
    }

    func recordRemoteScanID(_ remoteScanID: String, forScan scanID: UUID) async {
        guard var updated = manifest, updated.scanID == scanID, updated.remoteScanID == nil else { return }
        updated.remoteScanID = remoteScanID
        manifest = updated
        await save(updated)
    }

    func mergeServerFindings(_ findings: [Finding]) {
        serverFindings = FindingMerge.upsert(findings, into: serverFindings)
    }
}

private struct StateWaiter {
    let condition: (CaptureState) -> Bool
    let continuation: CheckedContinuation<Void, Never>
}
