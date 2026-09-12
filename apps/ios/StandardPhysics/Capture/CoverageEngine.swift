import Foundation
import simd

enum SurfaceConfidence: String, Codable {
    case low
    case medium
    case high
}

struct SurfaceSnapshot: Identifiable {
    let id: UUID
    let width: Float
    let height: Float
    let transform: simd_float4x4
    let confidence: SurfaceConfidence
    let isWall: Bool

    init(
        id: UUID,
        width: Float,
        height: Float,
        transform: simd_float4x4,
        confidence: SurfaceConfidence,
        isWall: Bool = true
    ) {
        self.id = id
        self.width = width
        self.height = height
        self.transform = transform
        self.confidence = confidence
        self.isWall = isWall
    }

    var center: SIMD3<Float> {
        SIMD3(transform.columns.3.x, transform.columns.3.y, transform.columns.3.z)
    }
}

struct CameraObservation {
    let transform: simd_float4x4
    let intrinsics: simd_float3x3
    let imageResolution: SIMD2<Float>

    var position: SIMD3<Float> {
        SIMD3(transform.columns.3.x, transform.columns.3.y, transform.columns.3.z)
    }

    static func lookingStraightAhead(position: SIMD3<Float>) -> CameraObservation {
        var transform = matrix_identity_float4x4
        transform.columns.3 = SIMD4(position, 1)
        return CameraObservation(
            transform: transform,
            intrinsics: simd_float3x3(
                SIMD3(500, 0, 0),
                SIMD3(0, 500, 0),
                SIMD3(500, 500, 1)
            ),
            imageResolution: SIMD2(1_000, 1_000)
        )
    }
}

struct SurfaceCoverage: Identifiable, Codable, Equatable {
    let id: UUID
    let observedFraction: Double
    let viewpointCount: Int
    let highConfidence: Bool

    enum CodingKeys: String, CodingKey {
        case id = "node_id"
        case observedFraction = "observed_fraction"
        case viewpointCount = "viewpoint_count"
    }

    var isDone: Bool {
        observedFraction >= 0.70 && viewpointCount >= 2 && highConfidence
    }

    init(
        id: UUID,
        observedFraction: Double,
        viewpointCount: Int,
        highConfidence: Bool
    ) {
        self.id = id
        self.observedFraction = observedFraction
        self.viewpointCount = viewpointCount
        self.highConfidence = highConfidence
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(UUID.self, forKey: .id)
        observedFraction = try container.decode(Double.self, forKey: .observedFraction)
        viewpointCount = try container.decode(Int.self, forKey: .viewpointCount)
        highConfidence = false
    }
}

struct CoverageSnapshot {
    var surfaces: [SurfaceCoverage] = []
    var unfinishedDirection: CoverageAngle = .zero

    var isComplete: Bool {
        !surfaces.isEmpty && surfaces.allSatisfy(\.isDone)
    }
}

struct CoverageAngle: Equatable {
    let radians: Double

    static let zero = CoverageAngle(radians: 0)
}

struct CoverageEngine {
    private struct ObservationState {
        var observedCells: Set<Int> = []
        var viewpoints: [SIMD3<Float>] = []
    }

    private let gridSize: Int
    private var observations: [UUID: ObservationState] = [:]
    private(set) var snapshot = CoverageSnapshot()

    init(gridSize: Int = 10) {
        precondition(gridSize > 0)
        self.gridSize = gridSize
    }

    mutating func reset() {
        observations.removeAll()
        snapshot = CoverageSnapshot()
    }

    mutating func update(surfaces: [SurfaceSnapshot], camera: CameraObservation) {
        for surface in surfaces {
            observe(surface: surface, from: camera)
        }

        snapshot.surfaces = surfaces.map { surface in
            let state = observations[surface.id, default: ObservationState()]
            return SurfaceCoverage(
                id: surface.id,
                observedFraction: Double(state.observedCells.count) / Double(gridSize * gridSize),
                viewpointCount: state.viewpoints.count,
                highConfidence: surface.confidence == .high
            )
        }
        snapshot.unfinishedDirection = directionToNearestUnfinishedSurface(
            surfaces: surfaces,
            camera: camera
        )
    }

    private mutating func observe(surface: SurfaceSnapshot, from camera: CameraObservation) {
        var state = observations[surface.id, default: ObservationState()]
        let visibleCells = visibleCellIndices(on: surface, from: camera)
        guard !visibleCells.isEmpty else { return }

        state.observedCells.formUnion(visibleCells)
        if state.viewpoints.allSatisfy({ simd_distance($0, camera.position) >= 1 }) {
            state.viewpoints.append(camera.position)
        }
        observations[surface.id] = state
    }

    private func visibleCellIndices(
        on surface: SurfaceSnapshot,
        from camera: CameraObservation
    ) -> Set<Int> {
        var visible: Set<Int> = []
        for row in 0..<gridSize {
            for column in 0..<gridSize {
                let localPoint = localPoint(on: surface, row: row, column: column)
                let worldPoint = surface.transform * localPoint
                if isVisible(
                    worldPoint: SIMD3(worldPoint.x, worldPoint.y, worldPoint.z),
                    surface: surface,
                    camera: camera
                ) {
                    visible.insert(row * gridSize + column)
                }
            }
        }
        return visible
    }

    private func localPoint(
        on surface: SurfaceSnapshot,
        row: Int,
        column: Int
    ) -> SIMD4<Float> {
        let x = (Float(column) + 0.5) / Float(gridSize) - 0.5
        let y = (Float(row) + 0.5) / Float(gridSize) - 0.5
        return SIMD4(x * surface.width, y * surface.height, 0, 1)
    }

    private func isVisible(
        worldPoint: SIMD3<Float>,
        surface: SurfaceSnapshot,
        camera: CameraObservation
    ) -> Bool {
        let pointToCamera = camera.position - worldPoint
        let distance = simd_length(pointToCamera)
        guard distance <= 5, distance > 0 else { return false }

        let normal = simd_normalize(
            SIMD3(surface.transform.columns.2.x, surface.transform.columns.2.y, surface.transform.columns.2.z)
        )
        guard abs(simd_dot(normal, pointToCamera / distance)) >= 0.5 else { return false }

        let cameraPoint = simd_inverse(camera.transform) * SIMD4(worldPoint, 1)
        guard cameraPoint.z < 0 else { return false }

        let depth = -cameraPoint.z
        let x = camera.intrinsics.columns.0.x * cameraPoint.x / depth
            + camera.intrinsics.columns.2.x
        let y = camera.intrinsics.columns.1.y * cameraPoint.y / depth
            + camera.intrinsics.columns.2.y
        return x >= 0 && x <= camera.imageResolution.x
            && y >= 0 && y <= camera.imageResolution.y
    }

    private func directionToNearestUnfinishedSurface(
        surfaces: [SurfaceSnapshot],
        camera: CameraObservation
    ) -> CoverageAngle {
        let coverageByID = Dictionary(uniqueKeysWithValues: snapshot.surfaces.map { ($0.id, $0) })
        let nearest = surfaces
            .filter { coverageByID[$0.id]?.isDone != true }
            .min { simd_distance($0.center, camera.position) < simd_distance($1.center, camera.position) }
        guard let nearest else { return .zero }

        let worldDirection = nearest.center - camera.position
        let cameraDirection = simd_inverse(camera.transform) * SIMD4(worldDirection, 0)
        return CoverageAngle(radians: Double(atan2(cameraDirection.x, -cameraDirection.z)))
    }
}
