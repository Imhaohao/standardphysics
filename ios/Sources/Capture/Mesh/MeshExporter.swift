import ARKit
import Foundation

nonisolated enum MeshExporter {
    /// Runs on the caller's actor and only copies bytes; ARKit's buffers are not touched afterwards.
    static func parts(of anchors: [ARMeshAnchor]) -> [MeshPart] {
        anchors.map(part(of:))
    }

    /// Merges parts carried over from before a relaunch with the live ones and encodes `mesh.spm`
    /// off the main actor.
    @concurrent
    static func encode(_ parts: [MeshPart], carriedOver: Data?) async -> Data {
        let liveIDs = Set(parts.map(\.id))
        let previous = carriedOver.flatMap { try? SPMFormat.decode($0) }?.parts ?? []
        let merged = previous.filter { !liveIDs.contains($0.id) } + parts
        return SPMFormat.encode(SPMMesh(floorY: FloorEstimator.floorY(of: merged), parts: merged))
    }

    private static func part(of anchor: ARMeshAnchor) -> MeshPart {
        let geometry = anchor.geometry
        let vertices = geometry.vertices
        let faces = geometry.faces
        return MeshPart(
            id: anchor.identifier,
            transform: anchor.transform,
            vertices: GeometryPacking.packFloat3(vertices.buffer.contents(), count: vertices.count, stride: vertices.stride, offset: vertices.offset),
            indices: GeometryPacking.packTriangles(faces.buffer.contents(), faceCount: faces.count, bytesPerIndex: faces.bytesPerIndex),
            classification: geometry.classification.map {
                GeometryPacking.packBytes($0.buffer.contents(), count: $0.count, stride: $0.stride, offset: $0.offset)
            }
        )
    }
}
