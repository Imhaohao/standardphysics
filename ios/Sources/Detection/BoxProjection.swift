import CoreGraphics
import simd

/// Projects a RoomPlan box into a camera image: the inverse of `DepthLifter.worldPoint`.
nonisolated enum BoxProjection {
    /// Points closer than this to the camera plane are treated as behind it.
    static let nearPlane: Float = 0.05
    /// A box may poke this fraction of the image past each edge and still count as in view.
    static let edgeSlack: CGFloat = 0.03

    /// Pixel position (origin top-left) of a world point, or nil when it is behind the camera.
    static func project(_ world: SIMD3<Float>, camera: CameraGeometry) -> SIMD2<Float>? {
        let cameraPoint = camera.cameraToWorld.inverse * SIMD4(world, 1)
        let distance = -cameraPoint.z
        guard distance > nearPlane else { return nil }
        let focal = SIMD2(camera.intrinsics[0][0], camera.intrinsics[1][1])
        let principal = SIMD2(camera.intrinsics[2][0], camera.intrinsics[2][1])
        let offset = SIMD2(cameraPoint.x, -cameraPoint.y) / distance
        return principal + offset * focal
    }

    /// The eight corners of a box given by its transform (centre and rotation) and full size.
    static func corners(transform: simd_float4x4, dimensions: SIMD3<Float>) -> [SIMD3<Float>] {
        let half = dimensions / 2
        let signs: [Float] = [-1, 1]
        return signs.flatMap { x -> [SIMD3<Float>] in
            signs.flatMap { y -> [SIMD3<Float>] in
                signs.map { z -> SIMD3<Float> in
                    let world = transform * SIMD4(x * half.x, y * half.y, z * half.z, 1)
                    return SIMD3(world.x, world.y, world.z)
                }
            }
        }
    }

    /// The pixel rectangle the box covers, when every corner is in front of the camera and
    /// inside the image (within `edgeSlack`); nil otherwise.
    static func visibleRect(transform: simd_float4x4, dimensions: SIMD3<Float>, camera: CameraGeometry) -> CGRect? {
        let projected = corners(transform: transform, dimensions: dimensions).map { project($0, camera: camera) }
        let pixels = projected.compactMap { $0 }
        guard pixels.count == projected.count, let first = pixels.first else { return nil }
        let lower = pixels.reduce(first) { simd_min($0, $1) }
        let upper = pixels.reduce(first) { simd_max($0, $1) }
        let rect = CGRect(
            x: CGFloat(lower.x), y: CGFloat(lower.y),
            width: CGFloat(upper.x - lower.x), height: CGFloat(upper.y - lower.y)
        )
        return isInside(rect, imageSize: camera.imageSize) ? rect : nil
    }

    static func isInside(_ rect: CGRect, imageSize: SIMD2<Float>) -> Bool {
        let width = CGFloat(imageSize.x)
        let height = CGFloat(imageSize.y)
        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
            .insetBy(dx: -width * edgeSlack, dy: -height * edgeSlack)
        return bounds.contains(rect)
    }
}
