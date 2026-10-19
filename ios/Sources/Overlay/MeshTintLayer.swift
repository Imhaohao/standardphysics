import ARKit
import RealityKit

/// Tints the LiDAR mesh by surface class. Copies geometry on main, groups triangles off main,
/// and only rebuilds anchors whose geometry changed.
final class MeshTintLayer {
    static let anchorsPerRefresh = 6

    private struct MeshJob: Sendable {
        let anchorID: UUID
        let transform: simd_float4x4
        let positions: [SIMD3<Float>]
        let mesh: MeshSnapshot
    }

    private struct GroupedMesh: Sendable {
        let job: MeshJob
        let indicesBySurface: [MeshSurface: [UInt32]]
    }

    let root = Entity()
    private var entities: [UUID: Entity] = [:]
    private var signatures: [UUID: Int] = [:]
    private var isBuilding = false
    private lazy var materials: [MeshSurface: UnlitMaterial] = MeshSurface.allCases.reduce(into: [:]) { materials, surface in
        materials[surface] = OverlayStyle.meshTint(for: surface).map { OverlayAssets.material($0) }
    }

    func refresh(with anchors: [ARMeshAnchor]) {
        guard !isBuilding else { return }
        removeVanished(keeping: Set(anchors.map(\.identifier)))
        let changed = anchors.filter { signatures[$0.identifier] != Self.signature(of: $0.geometry) }.prefix(Self.anchorsPerRefresh)
        guard !changed.isEmpty else { return }
        let jobs = changed.map(Self.job(for:))
        changed.forEach { signatures[$0.identifier] = Self.signature(of: $0.geometry) }
        isBuilding = true
        let tinted = Set(materials.keys)
        Task {
            let grouped = await Self.group(jobs, tinted: tinted)
            grouped.forEach(install)
            isBuilding = false
        }
    }

    private func removeVanished(keeping current: Set<UUID>) {
        for id in entities.keys where !current.contains(id) {
            entities.removeValue(forKey: id)?.removeFromParent()
            signatures[id] = nil
        }
    }

    private func install(_ grouped: GroupedMesh) {
        entities[grouped.job.anchorID]?.removeFromParent()
        let container = Entity()
        container.transform = Transform(matrix: grouped.job.transform)
        for (surface, indices) in grouped.indicesBySurface {
            guard let material = materials[surface], let model = Self.model(positions: grouped.job.positions, indices: indices, material: material) else { continue }
            container.addChild(model)
        }
        root.addChild(container)
        entities[grouped.job.anchorID] = container
    }

    private static func model(positions: [SIMD3<Float>], indices: [UInt32], material: UnlitMaterial) -> ModelEntity? {
        var descriptor = MeshDescriptor(name: "tint")
        descriptor.positions = MeshBuffers.Positions(positions)
        descriptor.primitives = .triangles(indices)
        guard let mesh = try? MeshResource.generate(from: [descriptor]) else { return nil }
        return ModelEntity(mesh: mesh, materials: [material])
    }

    @concurrent
    private static func group(_ jobs: [MeshJob], tinted: Set<MeshSurface>) async -> [GroupedMesh] {
        jobs.map { GroupedMesh(job: $0, indicesBySurface: MeshClassificationGrouper.indicesBySurface($0.mesh, tinted: tinted)) }
    }

    private static func signature(of geometry: ARMeshGeometry) -> Int {
        geometry.faces.count &* 65_537 &+ geometry.vertices.count
    }

    private static func job(for anchor: ARMeshAnchor) -> MeshJob {
        let geometry = anchor.geometry
        return MeshJob(
            anchorID: anchor.identifier,
            transform: anchor.transform,
            positions: positions(of: geometry.vertices),
            mesh: MeshSnapshot(triangleIndices: triangleIndices(of: geometry.faces), triangleSurfaces: surfaces(of: geometry.classification))
        )
    }

    private static func positions(of source: ARGeometrySource) -> [SIMD3<Float>] {
        let base = UnsafeRawPointer(source.buffer.contents()).advanced(by: source.offset)
        return (0..<source.count).map { index in
            let vertex = base.advanced(by: index * source.stride)
            return SIMD3(
                vertex.loadUnaligned(as: Float.self),
                vertex.loadUnaligned(fromByteOffset: 4, as: Float.self),
                vertex.loadUnaligned(fromByteOffset: 8, as: Float.self)
            )
        }
    }

    private static func triangleIndices(of faces: ARGeometryElement) -> [UInt32] {
        let base = UnsafeRawPointer(faces.buffer.contents())
        let indexCount = faces.count * faces.indexCountPerPrimitive
        guard faces.bytesPerIndex == MemoryLayout<UInt16>.size else {
            return (0..<indexCount).map { base.loadUnaligned(fromByteOffset: $0 * 4, as: UInt32.self) }
        }
        return (0..<indexCount).map { UInt32(base.loadUnaligned(fromByteOffset: $0 * 2, as: UInt16.self)) }
    }

    private static func surfaces(of source: ARGeometrySource?) -> [UInt8] {
        guard let source else { return [] }
        let base = UnsafeRawPointer(source.buffer.contents()).advanced(by: source.offset)
        return (0..<source.count).map { base.load(fromByteOffset: $0 * source.stride, as: UInt8.self) }
    }
}
