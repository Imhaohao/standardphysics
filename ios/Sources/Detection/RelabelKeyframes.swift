import ARKit
import CoreImage
import Foundation
import ImageIO
import Synchronization

/// One camera frame kept for cropping RoomPlan objects later: a JPEG in the sensor's own
/// (landscape) orientation, and the camera that took it.
nonisolated struct Keyframe: Sendable {
    let jpeg: Data
    /// Intrinsics are in pixels of `camera.imageSize`, the full captured image.
    let camera: CameraGeometry
    /// JPEG pixels per captured-image pixel.
    let scale: CGFloat
}

/// Frames sampled across one room's capture. Sampling starts at one frame per `startInterval`;
/// when the ring is full, every other frame goes and the interval doubles, so the frames stay
/// spread over the whole room however long it takes to scan.
nonisolated struct KeyframeRing<Frame: Sendable>: Sendable {
    let capacity: Int
    let startInterval: TimeInterval
    private(set) var frames: [Frame] = []
    private(set) var interval: TimeInterval
    private var lastSampled: TimeInterval?

    init(capacity: Int = 32, startInterval: TimeInterval = 1) {
        precondition(capacity >= 2, "a ring keeps at least two frames")
        self.capacity = capacity
        self.startInterval = startInterval
        interval = startInterval
    }

    func isDue(at timestamp: TimeInterval) -> Bool {
        guard let lastSampled else { return true }
        return timestamp - lastSampled >= interval
    }

    mutating func markSampled(at timestamp: TimeInterval) {
        lastSampled = timestamp
    }

    mutating func append(_ frame: Frame) {
        if frames.count >= capacity {
            frames = frames.enumerated().filter { $0.offset.isMultiple(of: 2) }.map(\.element)
            interval *= 2
        }
        frames.append(frame)
    }

    mutating func reset() {
        self = KeyframeRing(capacity: capacity, startInterval: startInterval)
    }
}

/// Keeps a spread of JPEG keyframes from the live camera. Feed it every polled frame from the
/// main actor; encoding happens off it, one frame at a time.
nonisolated final class KeyframeRecorder: Sendable {
    private struct State {
        var ring = KeyframeRing<Keyframe>()
        var isEncoding = false
    }

    private let state = Mutex(State())

    func consider(_ frame: ARFrame) {
        let timestamp = frame.timestamp
        let admitted = state.withLock { state in
            guard !state.isEncoding, state.ring.isDue(at: timestamp) else { return false }
            state.isEncoding = true
            state.ring.markSampled(at: timestamp)
            return true
        }
        guard admitted else { return }
        let image = CVPixelBufferWrapper(buffer: frame.capturedImage)
        let camera = Self.camera(of: frame)
        Task { await self.encode(image, camera: camera) }
    }

    func recent() -> [Keyframe] {
        state.withLock { $0.ring.frames }
    }

    func reset() {
        state.withLock { $0.ring.reset() }
    }

    @concurrent
    private func encode(_ image: CVPixelBufferWrapper, camera: CameraGeometry) async {
        let keyframe = await KeyframeEncoder.keyframe(from: image, camera: camera)
        state.withLock { state in
            if let keyframe { state.ring.append(keyframe) }
            state.isEncoding = false
        }
    }

    private static func camera(of frame: ARFrame) -> CameraGeometry {
        let resolution = frame.camera.imageResolution
        return CameraGeometry(
            intrinsics: frame.camera.intrinsics,
            imageSize: SIMD2(Float(resolution.width), Float(resolution.height)),
            cameraToWorld: frame.camera.transform
        )
    }
}

nonisolated enum KeyframeEncoder {
    static let longestSide: CGFloat = 1440
    static let quality: CGFloat = 0.7

    private static let context = CIContext(options: [.cacheIntermediates: false])

    @concurrent
    static func keyframe(from frame: CVPixelBufferWrapper, camera: CameraGeometry) async -> Keyframe? {
        let image = CIImage(cvPixelBuffer: frame.buffer)
        let scale = min(1, longestSide / max(image.extent.width, image.extent.height))
        let scaled = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        guard let jpeg = jpeg(scaled, quality: quality) else { return nil }
        return Keyframe(jpeg: jpeg, camera: camera, scale: scale)
    }

    static func jpeg(_ image: CIImage, quality: CGFloat) -> Data? {
        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) else { return nil }
        let options = [CIImageRepresentationOption(rawValue: kCGImageDestinationLossyCompressionQuality as String): quality]
        return context.jpegRepresentation(of: image, colorSpace: colorSpace, options: options)
    }
}
