import ARKit
import RoomPlan
import SwiftUI

/// The real app: one capture coordinator, the live overlay fed from it, the detector fed from
/// the camera, and the Rust engine checking each finished room.
@MainActor
final class LiveServices {
    static let framePollInterval: Duration = .milliseconds(33)

    let coordinator: CaptureCoordinator
    let sceneModel = LiveSceneModel()
    let appModel: AppModel
    private let detection: LiveDetectionPipeline
    private let keyframes: KeyframeRecorder
    private let streamer: ScanStreamer?
    let uploader: BackgroundUploader?
    private var frameFeed: Task<Void, Never>?
    private var sceneSync: Task<Void, Never>?

    init() {
        let coordinator = CaptureCoordinator()
        let journal = FileScanJournal()
        coordinator.onRoomFinished = { roomJSON, detectedObjects in
            let clock = ContinuousClock()
            let start = clock.now
            let findings = try await RustComplianceEngine().evaluateRoom(capturedRoomJSON: roomJSON, detectedObjects: detectedObjects)
            let elapsed = clock.now - start
            Diagnostics.shared.record("room_checked", [
                "ms": Double(elapsed.components.seconds) * 1000 + Double(elapsed.components.attoseconds) / 1e15,
                "findings": Double(findings.count),
                "fails": Double(findings.filter { $0.status == .fail }.count),
                "room_bytes": Double(roomJSON.count),
                "detector_objects": Double(detectedObjects.count),
            ])
            return findings
        }
        let keyframes = KeyframeRecorder()
        coordinator.makeRelabelCrops = { roomJSON in
            defer { keyframes.reset() }
            guard let room = CapturedRoomGeometry(capturedRoomJSON: roomJSON) else { return [] }
            return await RelabelCropper.crops(for: room, keyframes: keyframes.recent())
        }
        self.keyframes = keyframes
        self.coordinator = coordinator
        let api = try? APIClient.fromInfoPlist()
        let uploader = api.flatMap { try? BackgroundUploader.makeDefault(api: $0) }
        let streamer = Self.makeStreamer(api: api, uploader: uploader, journal: journal)
        coordinator.observer = streamer
        self.streamer = streamer
        self.uploader = uploader
        let local = OnDeviceScanProcessor(journal: journal)
        appModel = AppModel(
            capture: coordinator,
            processor: TimedProcessor(base: Self.makeProcessor(local: local, journal: journal, api: api, uploader: uploader, streamer: streamer)),
            journal: journal,
            account: AccountModel(service: api),
            reportStore: FileReportStore(),
            library: api,
            recheck: local,
            webBaseURL: WebLinks.baseURL(),
            canScan: RoomCaptureSession.isSupported
        )
        detection = LiveDetectionPipeline(detector: TimedDetector(base: CoreMLDetector())) { [weak coordinator] detections in
            await MainActor.run { coordinator?.ingest(detections) }
        }
    }

    private static func makeStreamer(api: APIClient?, uploader: BackgroundUploader?, journal: FileScanJournal) -> ScanStreamer? {
        guard let api, let uploader else { return nil }
        let tokens = KeychainTokenStore()
        return ScanStreamer(dependencies: ScanStreamer.Dependencies(
            creator: api,
            uploader: uploader,
            makeChannel: { LiveChannel.forScan($0, api: api) },
            isSignedIn: { tokens.token() != nil },
            directory: { journal.directory(for: $0) },
            cropUploader: api
        ))
    }

    private static func makeProcessor(
        local: OnDeviceScanProcessor, journal: FileScanJournal, api: APIClient?, uploader: BackgroundUploader?, streamer: ScanStreamer?
    ) -> any ScanProcessing {
        let tokens = KeychainTokenStore()
        guard let api, let uploader else { return local }
        Task { await uploader.start() }
        return PreferredScanProcessor(
            remote: ServerScanProcessor(
                api: api, uploader: uploader, rooms: streamer, retention: journal,
                roomDirectory: { journal.directory(for: $0) }
            ),
            local: local,
            isSignedIn: { tokens.token() != nil }
        )
    }

    /// Polls the session's current frame rather than taking the delegate, which RoomPlan may own.
    func startFrameFeed() {
        guard frameFeed == nil else { return }
        frameFeed = Task { [weak self] in
            while !Task.isCancelled {
                self?.feedCurrentFrame()
                try? await Task.sleep(for: Self.framePollInterval)
            }
        }
        sceneSync = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                self.sceneModel.update(from: self.coordinator)
                self.recordPhaseChange()
                try? await Task.sleep(for: .milliseconds(100))
            }
        }
    }

    func stopFrameFeed() {
        frameFeed?.cancel()
        sceneSync?.cancel()
        frameFeed = nil
        sceneSync = nil
    }

    private var lastRecordedPhase: CapturePhase?

    private func recordPhaseChange() {
        let phase = coordinator.phase
        guard phase != lastRecordedPhase else { return }
        lastRecordedPhase = phase
        Diagnostics.shared.record("phase", [
            "elements": Double(coordinator.liveElements.count),
            "findings": Double(coordinator.provisionalFindings.count),
        ], note: String(describing: phase))
    }

    private func feedCurrentFrame() {
        guard case .scanning = coordinator.phase, let frame = coordinator.arSession?.currentFrame else { return }
        detection.consider(frame)
        keyframes.consider(frame)
    }
}

struct LiveCameraLayer: View {
    let services: LiveServices

    var body: some View {
        Group {
            if let session = services.coordinator.arSession {
                LiveSceneView(session: session, model: services.sceneModel)
            } else {
                CameraPlaceholder()
            }
        }
        .onAppear { services.startFrameFeed() }
        .onDisappear { services.stopFrameFeed() }
    }
}
