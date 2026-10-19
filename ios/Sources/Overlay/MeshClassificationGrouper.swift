/// LiDAR mesh surface classes, matching `ARMeshClassification` raw values.
nonisolated enum MeshSurface: UInt8, Sendable, CaseIterable {
    case none = 0
    case wall = 1
    case floor = 2
    case ceiling = 3
    case table = 4
    case seat = 5
    case window = 6
    case door = 7
}

/// One mesh anchor's triangles copied out of ARKit's Metal buffers.
nonisolated struct MeshSnapshot: Sendable, Equatable {
    let triangleIndices: [UInt32]
    /// One class per triangle; empty when the session does not classify.
    let triangleSurfaces: [UInt8]
}

nonisolated enum MeshClassificationGrouper {
    /// Triangle indices for each tinted surface class. Triangles of untinted classes are dropped.
    static func indicesBySurface(_ mesh: MeshSnapshot, tinted: Set<MeshSurface>) -> [MeshSurface: [UInt32]] {
        let triangleCount = mesh.triangleIndices.count / 3
        return (0..<triangleCount).reduce(into: [MeshSurface: [UInt32]]()) { groups, triangle in
            let surface = surface(of: triangle, in: mesh)
            guard tinted.contains(surface) else { return }
            groups[surface, default: []].append(contentsOf: mesh.triangleIndices[triangle * 3..<triangle * 3 + 3])
        }
    }

    private static func surface(of triangle: Int, in mesh: MeshSnapshot) -> MeshSurface {
        guard mesh.triangleSurfaces.indices.contains(triangle) else { return .none }
        return MeshSurface(rawValue: mesh.triangleSurfaces[triangle]) ?? .none
    }
}
