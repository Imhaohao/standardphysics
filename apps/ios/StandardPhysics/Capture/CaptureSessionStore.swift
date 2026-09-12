import ARKit
import RoomPlan
import SwiftUI

@MainActor
final class CaptureSessionStore: ObservableObject {
    enum Phase: Equatable {
        case preparing
        case scanning
        case processing
        case ready
        case failed(String)
    }

    @Published private(set) var phase: Phase = .preparing
    @Published private(set) var coverage = CoverageSnapshot()
    @Published private(set) var surfaces: [SurfaceSnapshot] = []
    @Published private(set) var instruction = "Turn around slowly"
    @Published private(set) var capturedScan: CapturedScan?

    private(set) var captureDirectory: URL?
    weak var controller: RoomCaptureController?

    func attach(_ controller: RoomCaptureController) {
        guard self.controller == nil else { return }
        self.controller = controller
        do {
            let directory = try ScanExporter.makeCaptureDirectory()
            captureDirectory = directory
            try controller.start(in: directory)
            phase = .scanning
        } catch {
            phase = .failed("Try the scan again.")
        }
    }

    func finish() {
        guard phase == .scanning else { return }
        phase = .processing
        instruction = "Building your room"
        controller?.finish()
    }

    func cancel() {
        controller?.cancel()
    }

    fileprivate func didUpdate(
        coverage: CoverageSnapshot,
        surfaces: [SurfaceSnapshot],
        instruction: String?
    ) {
        self.coverage = coverage
        self.surfaces = surfaces
        if coverage.isComplete {
            self.instruction = "You’ve got the whole shop."
        } else if let instruction {
            self.instruction = instruction
        }
    }

    fileprivate func didFinish(_ result: Result<CapturedScan, Error>) {
        switch result {
        case .success(let scan):
            capturedScan = scan
            phase = .ready
        case .failure:
            phase = .failed("Save this scan and try again.")
        }
    }
}

struct RoomCaptureContainer: UIViewControllerRepresentable {
    @ObservedObject var store: CaptureSessionStore

    func makeUIViewController(context: Context) -> RoomCaptureController {
        let controller = RoomCaptureController(store: store)
        controller.loadViewIfNeeded()
        store.attach(controller)
        return controller
    }

    func updateUIViewController(_ uiViewController: RoomCaptureController, context: Context) {}
}

final class RoomCaptureController: UIViewController, RoomCaptureViewDelegate, RoomCaptureSessionDelegate {
    private let captureView = RoomCaptureView(frame: .zero)
    private unowned let store: CaptureSessionStore
    private var recorder: FrameRecorder?
    private var coverageEngine = CoverageEngine()
    private var latestCoverage = CoverageSnapshot()
    private var recordingResult: RecordingResult?
    private var processedRoom: CapturedRoom?
    private var captureDirectory: URL?
    private var hasFinished = false

    init(store: CaptureSessionStore) {
        self.store = store
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        captureView.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(captureView)
        NSLayoutConstraint.activate([
            captureView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            captureView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            captureView.topAnchor.constraint(equalTo: view.topAnchor),
            captureView.bottomAnchor.constraint(equalTo: view.bottomAnchor)
        ])
        captureView.delegate = self
        captureView.captureSession.delegate = self
    }

    func start(in directory: URL) throws {
        captureDirectory = directory
        let recorder = try FrameRecorder(session: captureView.captureSession.arSession, directory: directory)
        recorder.onTimeLimit = { [weak self] in self?.store.finish() }
        self.recorder = recorder
        coverageEngine.reset()
        var configuration = RoomCaptureSession.Configuration()
        configuration.isCoachingEnabled = true
        captureView.captureSession.run(configuration: configuration)
        recorder.start()
    }

    func finish() {
        guard !hasFinished else { return }
        hasFinished = true
        captureView.captureSession.stop(pauseARSession: true)
        recorder?.stop { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let recording):
                self.recordingResult = recording
                self.exportIfReady()
            case .failure(let error):
                self.store.didFinish(.failure(error))
            }
        }
    }

    func cancel() {
        captureView.captureSession.stop(pauseARSession: true)
        let directory = captureDirectory
        recorder?.stop { _ in
            if let directory { try? FileManager.default.removeItem(at: directory) }
        }
        recorder = nil
    }

    nonisolated func captureView(shouldPresent roomDataForProcessing: CapturedRoomData, error: Error?) -> Bool {
        error == nil
    }

    nonisolated func captureView(didPresent processedResult: CapturedRoom, error: Error?) {
        Task { @MainActor [weak self] in
            guard let self else { return }
            guard error == nil else {
                store.didFinish(.failure(CaptureProcessingError.failed))
                return
            }
            processedRoom = processedResult
            exportIfReady()
        }
    }

    nonisolated func captureSession(_ session: RoomCaptureSession, didUpdate room: CapturedRoom) {
        guard let frame = session.arSession.currentFrame else { return }
        let camera = CameraObservation(
            transform: frame.camera.transform,
            intrinsics: frame.camera.intrinsics,
            imageResolution: SIMD2(Float(frame.camera.imageResolution.width), Float(frame.camera.imageResolution.height))
        )
        Task { @MainActor [weak self] in self?.handleUpdate(room: room, camera: camera) }
    }

    nonisolated func captureSession(
        _ session: RoomCaptureSession,
        didProvide instruction: RoomCaptureSession.Instruction
    ) {
        let text = instruction.friendlyText
        Task { @MainActor [weak self] in
            guard let self else { return }
            store.didUpdate(coverage: latestCoverage, surfaces: store.surfaces, instruction: text)
        }
    }

    nonisolated func captureSession(_ session: RoomCaptureSession, didEndWith data: CapturedRoomData, error: Error?) {
        guard error != nil else { return }
        Task { @MainActor [weak self] in
            self?.store.didFinish(.failure(CaptureProcessingError.failed))
        }
    }

    private func handleUpdate(room: CapturedRoom, camera: CameraObservation) {
        let surfaces = snapshots(from: room)
        coverageEngine.update(surfaces: surfaces, camera: camera)
        latestCoverage = coverageEngine.snapshot
        store.didUpdate(coverage: latestCoverage, surfaces: surfaces, instruction: nil)
    }

    private func exportIfReady() {
        guard let room = processedRoom,
              let recording = recordingResult,
              let directory = captureDirectory else { return }
        let coverage = latestCoverage
        let exportTask = Task.detached(priority: .userInitiated) {
            Result {
                try ScanExporter.export(
                    room: room,
                    recording: recording,
                    coverage: coverage,
                    directory: directory
                )
            }
        }
        Task { @MainActor [weak self] in
            self?.store.didFinish(await exportTask.value)
        }
    }

    private func snapshots(from room: CapturedRoom) -> [SurfaceSnapshot] {
        let wallSnapshots = room.walls.map {
            SurfaceSnapshot(
                id: $0.identifier,
                width: $0.dimensions.x,
                height: max($0.dimensions.y, $0.dimensions.z),
                transform: $0.transform,
                confidence: SurfaceConfidence($0.confidence),
                isWall: true
            )
        }
        let otherSurfaces = room.doors + room.windows + room.openings + room.floors
        let otherSurfaceSnapshots = otherSurfaces.map {
            SurfaceSnapshot(
                id: $0.identifier,
                width: $0.dimensions.x,
                height: max($0.dimensions.y, $0.dimensions.z),
                transform: $0.transform,
                confidence: SurfaceConfidence($0.confidence),
                isWall: false
            )
        }
        let objectSnapshots = room.objects.map {
            SurfaceSnapshot(
                id: $0.identifier,
                width: $0.dimensions.x,
                height: $0.dimensions.y,
                transform: $0.transform,
                confidence: SurfaceConfidence($0.confidence),
                isWall: false
            )
        }
        return wallSnapshots + otherSurfaceSnapshots + objectSnapshots
    }
}

private enum CaptureProcessingError: Error {
    case failed
}

private extension SurfaceConfidence {
    init(_ confidence: CapturedRoom.Confidence) {
        switch confidence {
        case .low: self = .low
        case .medium: self = .medium
        case .high: self = .high
        @unknown default: self = .low
        }
    }
}

private extension RoomCaptureSession.Instruction {
    var friendlyText: String? {
        switch self {
        case .moveCloseToWall: "Walk closer to the wall"
        case .moveAwayFromWall: "Take one step back"
        case .slowDown: "Turn around slowly"
        case .turnOnLight: "Turn on more lights"
        case .lowTexture: "Point the phone at the wall ahead"
        case .normal: nil
        @unknown default: nil
        }
    }
}
