import ARKit

/// Feeds a throttled stream of ARFrames to a detector and lifts each result into the world.
/// Call `consider(_:)` from the ARSession delegate; results arrive on `onDetections`.
nonisolated final class LiveDetectionPipeline: Sendable {
    private let detector: any ObjectDetecting
    private let throttler: FrameThrottler
    private let onDetections: @Sendable ([Detection]) async -> Void

    init(
        detector: any ObjectDetecting = CoreMLDetector(),
        throttler: FrameThrottler = FrameThrottler(),
        onDetections: @escaping @Sendable ([Detection]) async -> Void
    ) {
        self.detector = detector
        self.throttler = throttler
        self.onDetections = onDetections
    }

    func consider(_ frame: ARFrame) {
        guard throttler.admit() else { return }
        let snapshot = FrameSnapshot(frame: frame)
        Task { await self.process(snapshot) }
    }

    func process(_ snapshot: FrameSnapshot) async {
        defer { throttler.finish() }
        guard let detections = try? await detector.detect(pixelBuffer: snapshot.image) else { return }
        await onDetections(detections.map { Self.lifted($0, in: snapshot) })
    }

    static func lifted(_ detection: Detection, in snapshot: FrameSnapshot) -> Detection {
        guard let depth = snapshot.depth,
              let box = DepthLifter.lift(boundingBox: detection.boundingBox, depth: depth, camera: snapshot.camera)
        else { return detection }
        return Detection(
            label: detection.label,
            category: detection.category,
            confidence: detection.confidence,
            boundingBox: detection.boundingBox,
            worldCenter: box.center,
            worldSize: box.size
        )
    }
}
