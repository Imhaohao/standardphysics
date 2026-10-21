import Foundation
import Observation

/// A stand-in `CaptureControlling` with no camera: it moves through the same phases the real
/// coordinator does, instantly, and carries sample findings.
@Observable
final class PreviewCaptureController: CaptureControlling {
    var phase: CapturePhase = .idle
    var manifest: ScanManifest?
    var liveElements: [LiveElement] = []
    var detections: [Detection] = []
    var provisionalFindings: [Finding] = []
    var guidance: String?
    var relocalizationSnapshot: Data?

    private var storedScans: [UUID: ScanManifest]
    private var demoTask: Task<Void, Never>?

    init(storedScans: [ScanManifest] = [SampleData.unfinishedManifest()], snapshot: Data? = nil) {
        self.storedScans = Dictionary(uniqueKeysWithValues: storedScans.map { ($0.scanID, $0) })
        relocalizationSnapshot = snapshot
    }

    var currentRoom: Int {
        (manifest?.rooms.count ?? 0) + 1
    }

    func startScan(name: String) async {
        manifest = ScanManifest(scanID: UUID(), name: name, startedAt: .now, phase: .scanning(room: 1), rooms: [])
        provisionalFindings = []
        enterScanning()
    }

    func resume(scanID: UUID) async {
        guard let stored = storedScans[scanID] else {
            phase = .failed(message: "This scan is no longer on this phone.")
            return
        }
        manifest = stored
        phase = .relocalizing(room: currentRoom)
        guidance = nil
    }

    func pause() {
        phase = .paused(room: currentRoom, reason: .user)
    }

    func continueScanning() {
        enterScanning()
    }

    func finishRoom() async {
        guard var manifest else { return }
        let index = manifest.rooms.count + 1
        manifest.rooms.append(RoomRecord(index: index, name: "Room \(index)", capturedRoomFile: "room-\(index).json", completedAt: .now))
        self.manifest = manifest
        phase = .betweenRooms(completed: index)
        guidance = nil
    }

    func nameRoom(index: Int, name: String) async {
        guard let position = manifest?.rooms.firstIndex(where: { $0.index == index }) else { return }
        manifest?.rooms[position].name = name
    }

    func restartRoom() {
        enterScanning()
    }

    func startNextRoom() {
        enterScanning()
    }

    func finishScan() async {
        phase = .finishing
        manifest?.phase = .finished
        phase = .finished
    }

    func discardScan() async {
        if let scanID = manifest?.scanID { storedScans[scanID] = nil }
        manifest = nil
        phase = .idle
    }

    func deleteScan(scanID: UUID) async {
        storedScans[scanID] = nil
        guard manifest?.scanID == scanID else { return }
        manifest = nil
        phase = .idle
    }

    /// Puts the controller straight into `phase` with believable surroundings, for previews.
    func stage(_ phase: CapturePhase, roomsSaved: Int = 1) {
        var manifest = SampleData.unfinishedManifest(roomsSaved: roomsSaved)
        manifest.phase = phase
        self.manifest = manifest
        self.phase = phase
        provisionalFindings = SampleData.provisionalFindings
        guidance = phase == .scanning(room: roomsSaved + 1) ? "Walk slowly along the counter" : nil
    }

    /// Loops through scanning, pausing and finishing so a preview shows every state.
    func runDemoCycle(step: Duration = .seconds(3)) {
        demoTask?.cancel()
        let phases: [CapturePhase] = [.scanning(room: 2), .paused(room: 2, reason: .user), .relocalizing(room: 2), .paused(room: 2, reason: .thermal), .betweenRooms(completed: 2)]
        demoTask = Task { [weak self] in
            for phase in phases {
                guard !Task.isCancelled else { return }
                self?.stage(phase)
                try? await Task.sleep(for: step)
            }
        }
    }

    private func enterScanning() {
        phase = .scanning(room: currentRoom)
        guidance = "Walk slowly along the walls"
    }
}
