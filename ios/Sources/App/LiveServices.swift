import ARKit
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
    private let streamer: ScanStreamer?
    let uploader: BackgroundUploader?
    private var frameFeed: Task<Void, Never>?
    private var sceneSync: Task<Void, Never>?

    init() {
        let coordinator = CaptureCoordinator()
        let journal = FileScanJournal()
        coordinator.onRoomFinished = { roomJSON in
            try await RustComplianceEngine().evaluateRoom(capturedRoomJSON: roomJSON)
        }
        self.coordinator = coordinator
        let api = try? APIClient.fromInfoPlist()
        let uploader = api.flatMap { try? BackgroundUploader.makeDefault(api: $0) }
        let streamer = Self.makeStreamer(api: api, uploader: uploader, journal: journal)
        coordinator.observer = streamer
        self.streamer = streamer
        self.uploader = uploader
        appModel = AppModel(
            capture: coordinator,
            processor: Self.makeProcessor(journal: journal, api: api, uploader: uploader, streamer: streamer),
            journal: journal,
            account: AccountModel(service: api)
        )
        detection = LiveDetectionPipeline(detector: CoreMLDetector()) { [weak coordinator] detections in
            await MainActor.run { coordinator?.detections = detections }
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
            directory: { journal.directory(for: $0) }
        ))
    }

    private static func makeProcessor(
        journal: FileScanJournal, api: APIClient?, uploader: BackgroundUploader?, streamer: ScanStreamer?
    ) -> any ScanProcessing {
        let local = OnDeviceScanProcessor(journal: journal)
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

    private func feedCurrentFrame() {
        guard case .scanning = coordinator.phase, let frame = coordinator.arSession?.currentFrame else { return }
        detection.consider(frame)
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
