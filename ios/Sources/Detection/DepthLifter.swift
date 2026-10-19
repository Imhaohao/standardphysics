import CoreGraphics
import simd

/// A copy of one frame's LiDAR depth, so the ARFrame itself can be released straight away.
nonisolated struct DepthSamples: Sendable, Equatable {
    static let minimumUsableConfidence: UInt8 = 1

    let width: Int
    let height: Int
    /// Metres along the camera's viewing axis, row-major, origin top-left.
    let depths: [Float]
    /// ARConfidenceLevel raw values per sample, or nil when the frame carries none.
    let confidences: [UInt8]?

    func isUsable(at index: Int) -> Bool {
        let depth = depths[index]
        guard depth.isFinite, depth > 0 else { return false }
        guard let confidences else { return true }
        return confidences.indices.contains(index) && confidences[index] >= Self.minimumUsableConfidence
    }
}

/// The captured camera image's geometry: intrinsics are in pixels of `imageSize`.
nonisolated struct CameraGeometry: Sendable, Equatable {
    let intrinsics: simd_float3x3
    let imageSize: SIMD2<Float>
    let cameraToWorld: simd_float4x4
}

nonisolated struct LiftedBox: Sendable, Equatable {
    let center: SIMD3<Float>
    /// Horizontal extent, vertical extent, depth extent, in metres.
    let size: SIMD3<Float>
}

/// Turns a 2D detection into an approximate world-space box using scene depth.
nonisolated enum DepthLifter {
    static let innerRegionFraction: CGFloat = 0.5
    static let minimumSampleCount = 4
    static let minimumDepthExtent: Float = 0.05

    /// `boundingBox` is normalized to the captured image, origin top-left.
    static func lift(boundingBox: CGRect, depth: DepthSamples, camera: CameraGeometry) -> LiftedBox? {
        let innerBox = boundingBox.insetBy(
            dx: boundingBox.width * (1 - innerRegionFraction) / 2,
            dy: boundingBox.height * (1 - innerRegionFraction) / 2
        )
        let innerSamples = usableDepths(in: innerBox, of: depth)
        guard innerSamples.count >= minimumSampleCount, let distance = median(innerSamples) else { return nil }

        let center = worldPoint(normalized: CGPoint(x: boundingBox.midX, y: boundingBox.midY), distance: distance, camera: camera)
        let corners = cornerPoints(of: boundingBox).map { worldPoint(normalized: $0, distance: distance, camera: camera) }
        let depthExtent = depthSpread(usableDepths(in: boundingBox, of: depth))
        let size = SIMD3(horizontalExtent(of: corners), verticalExtent(of: corners), depthExtent)
        return LiftedBox(center: center, size: size)
    }

    static func usableDepths(in normalizedRect: CGRect, of depth: DepthSamples) -> [Float] {
        let clamped = normalizedRect.intersection(CGRect(x: 0, y: 0, width: 1, height: 1))
        guard !clamped.isNull, !clamped.isEmpty, depth.depths.count == depth.width * depth.height else { return [] }
        let columns = pixelRange(clamped.minX, clamped.maxX, count: depth.width)
        let rows = pixelRange(clamped.minY, clamped.maxY, count: depth.height)
        return rows.flatMap { row in
            columns.compactMap { column in
                let index = row * depth.width + column
                return depth.isUsable(at: index) ? depth.depths[index] : nil
            }
        }
    }

    static func median(_ values: [Float]) -> Float? {
        guard !values.isEmpty else { return nil }
        let sorted = values.sorted()
        let middle = sorted.count / 2
        return sorted.count.isMultiple(of: 2) ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle]
    }

    /// ARKit's camera looks down -Z with +Y up, while image rows grow downward.
    static func worldPoint(normalized point: CGPoint, distance: Float, camera: CameraGeometry) -> SIMD3<Float> {
        let pixel = SIMD2(Float(point.x) * camera.imageSize.x, Float(point.y) * camera.imageSize.y)
        let focal = SIMD2(camera.intrinsics[0][0], camera.intrinsics[1][1])
        let principal = SIMD2(camera.intrinsics[2][0], camera.intrinsics[2][1])
        let offset = (pixel - principal) / focal * distance
        let cameraPoint = SIMD4(offset.x, -offset.y, -distance, 1)
        let world = camera.cameraToWorld * cameraPoint
        return SIMD3(world.x, world.y, world.z)
    }

    private static func pixelRange(_ lower: CGFloat, _ upper: CGFloat, count: Int) -> Range<Int> {
        let start = max(0, min(count - 1, Int((lower * CGFloat(count)).rounded(.down))))
        let end = max(start + 1, min(count, Int((upper * CGFloat(count)).rounded(.up))))
        return start..<end
    }

    private static func cornerPoints(of rect: CGRect) -> [CGPoint] {
        [
            CGPoint(x: rect.minX, y: rect.minY),
            CGPoint(x: rect.maxX, y: rect.minY),
            CGPoint(x: rect.maxX, y: rect.maxY),
            CGPoint(x: rect.minX, y: rect.maxY),
        ]
    }

    /// The image edge that lies flatter in the world is the object's width, whichever way the phone is held.
    private static func horizontalExtent(of corners: [SIMD3<Float>]) -> Float {
        let edges = [corners[1] - corners[0], corners[3] - corners[0]]
        let flattest = edges.min { verticalShare(of: $0) < verticalShare(of: $1) } ?? edges[0]
        return simd_length(flattest)
    }

    private static func verticalShare(of edge: SIMD3<Float>) -> Float {
        let length = simd_length(edge)
        return length > 0 ? abs(edge.y) / length : 1
    }

    private static func verticalExtent(of points: [SIMD3<Float>]) -> Float {
        let heights = points.map(\.y)
        return (heights.max() ?? 0) - (heights.min() ?? 0)
    }

    private static func depthSpread(_ samples: [Float]) -> Float {
        guard samples.count >= minimumSampleCount else { return minimumDepthExtent }
        let sorted = samples.sorted()
        let near = sorted[sorted.count / 10]
        let far = sorted[sorted.count * 9 / 10]
        return max(minimumDepthExtent, far - near)
    }
}
