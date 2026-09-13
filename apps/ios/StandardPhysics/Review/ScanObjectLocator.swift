import RoomPlan
import simd

struct ScanObjectLocator {
    private let objects: [SurfaceSnapshot]

    init(objects: [SurfaceSnapshot]) {
        self.objects = objects.filter { $0.kind != "wall" && $0.kind != "floor" }
    }

    func object(at point: SIMD3<Float>) -> SurfaceSnapshot? {
        let matches = objects.filter { object in
            guard case .box(let size) = object.shape else { return false }
            let local = simd_inverse(object.transform) * SIMD4(point, 1)
            let distance = simd_abs(SIMD3(local.x, local.y, local.z))
            let halfSize = size / 2 + SIMD3(repeating: 0.03)
            return distance.x <= halfSize.x && distance.y <= halfSize.y && distance.z <= halfSize.z
        }
        // Overlapping recognition boxes are ambiguous; keep the measured surface unlabelled.
        return matches.count == 1 ? matches.first : nil
    }
}
