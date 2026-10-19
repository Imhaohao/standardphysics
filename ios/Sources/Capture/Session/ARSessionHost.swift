import ARKit
import Foundation
import Synchronization

nonisolated enum ARSessionHostError: Error, Equatable {
    case missingWorldMap
    case unreadableWorldMap
}

protocol ARSessionHosting: AnyObject {
    var events: AsyncStream<ARHostEvent> { get }
    /// The single app-wide session, for RoomPlan and the overlay. `nil` in tests.
    var arSession: ARSession? { get }
    func run(_ mode: ARRunMode, worldMap: Data?) async throws
    func pause()
    /// `nil` when the map is not good enough to be worth saving right now.
    func checkpoint() async throws -> Checkpoint?
    func meshParts() -> [MeshPart]
}

/// Owns the one `ARSession`. Delegate callbacks arrive on a private queue and are republished
/// as `events`; per-frame work there is limited to the checkpoint clock.
final class ARSessionHost: ARSessionHosting {
    let session = ARSession()
    let events: AsyncStream<ARHostEvent>

    private let relay: ARSessionEventRelay
    private let delegateQueue = DispatchQueue(label: "com.tarunyadgirkar.standardphysics.ar-delegate", qos: .userInteractive)
    private var configuration: ARWorldTrackingConfiguration?
    private var hasRun = false

    init() {
        let (stream, continuation) = AsyncStream.makeStream(of: ARHostEvent.self, bufferingPolicy: .bufferingNewest(64))
        events = stream
        relay = ARSessionEventRelay(continuation: continuation)
        session.delegateQueue = delegateQueue
        session.delegate = relay
    }

    var arSession: ARSession? { session }

    static func makeConfiguration(initialWorldMap: ARWorldMap?) -> ARWorldTrackingConfiguration {
        let configuration = ARWorldTrackingConfiguration()
        if ARWorldTrackingConfiguration.supportsSceneReconstruction(.meshWithClassification) {
            configuration.sceneReconstruction = .meshWithClassification
        }
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
            configuration.frameSemantics.insert(.sceneDepth)
        }
        configuration.initialWorldMap = initialWorldMap
        return configuration
    }

    func run(_ mode: ARRunMode, worldMap: Data?) async throws {
        switch mode {
        case .continueExisting:
            session.run(configuration ?? Self.makeConfiguration(initialWorldMap: nil))
            hasRun = true
        case .fresh:
            start(Self.makeConfiguration(initialWorldMap: nil), options: [.resetTracking, .removeExistingAnchors])
        case .relocalize:
            guard let worldMap else { throw ARSessionHostError.missingWorldMap }
            let map = try await WorldMapCodec.unarchive(worldMap)
            start(Self.makeConfiguration(initialWorldMap: map.map), options: hasRun ? [.resetTracking, .removeExistingAnchors] : [])
        }
    }

    func pause() {
        session.pause()
    }

    func checkpoint() async throws -> Checkpoint? {
        guard let frame = session.currentFrame, frame.worldMappingStatus.isGoodEnoughToSave else { return nil }
        async let snapshot = SnapshotEncoder.jpeg(from: CVPixelBufferWrapper(buffer: frame.capturedImage))
        let worldMap = try await WorldMapCodec.archivedCurrentWorldMap(of: session)
        return Checkpoint(worldMap: worldMap, snapshotJPEG: await snapshot)
    }

    func meshParts() -> [MeshPart] {
        let anchors = session.currentFrame?.anchors.compactMap { $0 as? ARMeshAnchor } ?? []
        return MeshExporter.parts(of: anchors)
    }

    private func start(_ configuration: ARWorldTrackingConfiguration, options: ARSession.RunOptions) {
        self.configuration = configuration
        session.run(configuration, options: options)
        hasRun = true
    }
}

nonisolated final class ARSessionEventRelay: NSObject, ARSessionDelegate, Sendable {
    private let continuation: AsyncStream<ARHostEvent>.Continuation
    private let clock = Mutex(CheckpointClock())

    init(continuation: AsyncStream<ARHostEvent>.Continuation) {
        self.continuation = continuation
    }

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        let isMappingGood = frame.worldMappingStatus.isGoodEnoughToSave
        let timestamp = frame.timestamp
        if clock.withLock({ $0.isDue(at: timestamp, isMappingGood: isMappingGood) }) {
            continuation.yield(.checkpointDue)
        }
    }

    func session(_ session: ARSession, cameraDidChangeTrackingState camera: ARCamera) {
        continuation.yield(.tracking(TrackingStatus(camera.trackingState)))
    }

    func sessionWasInterrupted(_ session: ARSession) {
        continuation.yield(.interrupted)
    }

    func sessionInterruptionEnded(_ session: ARSession) {
        continuation.yield(.interruptionEnded)
    }

    func sessionShouldAttemptRelocalization(_ session: ARSession) -> Bool {
        true
    }

    func session(_ session: ARSession, didFailWithError error: any Error) {
        continuation.yield(.failed(message: error.localizedDescription))
    }
}

/// `ARWorldMap` is immutable once ARKit hands it over, so moving it between isolation domains is safe.
nonisolated struct WorldMapBox: @unchecked Sendable {
    let map: ARWorldMap
}

nonisolated enum WorldMapCodec {
    static func archive(_ map: ARWorldMap) throws -> Data {
        try NSKeyedArchiver.archivedData(withRootObject: map, requiringSecureCoding: true)
    }

    @concurrent
    static func unarchive(_ data: Data) async throws -> WorldMapBox {
        guard let map = try NSKeyedUnarchiver.unarchivedObject(ofClass: ARWorldMap.self, from: data) else {
            throw ARSessionHostError.unreadableWorldMap
        }
        return WorldMapBox(map: map)
    }

    /// The completion handler runs on an ARKit queue; archiving happens there, off the main actor.
    static func archivedCurrentWorldMap(of session: ARSession) async throws -> Data {
        try await withCheckedThrowingContinuation { continuation in
            session.getCurrentWorldMap { map, error in
                guard let map else {
                    continuation.resume(throwing: error ?? ARSessionHostError.missingWorldMap)
                    return
                }
                continuation.resume(with: Result { try archive(map) })
            }
        }
    }
}
