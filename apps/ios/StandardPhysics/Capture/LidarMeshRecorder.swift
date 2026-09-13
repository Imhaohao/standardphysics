import ARKit
import SceneKit

struct LidarMesh: Codable, Sendable {
    struct Part: Codable, Sendable {
        let id: UUID
        let transform: [Float]
        let vertices: [Float]
        let triangles: [UInt32]

        var isValid: Bool {
            transform.count == 16 && transform.allSatisfy(\.isFinite)
                && !vertices.isEmpty && vertices.count.isMultiple(of: 3)
                && vertices.allSatisfy(\.isFinite)
                && !triangles.isEmpty && triangles.count.isMultiple(of: 3)
                && triangles.allSatisfy { $0 < vertices.count / 3 }
        }
    }

    let parts: [Part]
    var peopleFilteringEnabled: Bool?
    var floorY: Float?

    var triangleCount: Int { parts.reduce(0) { $0 + $1.triangles.count / 3 } }

    init(parts: [Part], peopleFilteringEnabled: Bool? = nil, floorY: Float? = nil) {
        self.parts = parts.filter(\.isValid)
        self.peopleFilteringEnabled = peopleFilteringEnabled
        self.floorY = floorY
    }

    init(anchors: [ARMeshAnchor], peopleFilteringEnabled: Bool) {
        self.peopleFilteringEnabled = peopleFilteringEnabled
        parts = anchors.compactMap { anchor in
            let source = anchor.geometry.vertices
            let faces = anchor.geometry.faces
            guard source.componentsPerVector == 3, source.format == .float3,
                  faces.indexCountPerPrimitive == 3, [2, 4].contains(faces.bytesPerIndex) else { return nil }
            let vertices = (0..<source.count).flatMap { index -> [Float] in
                let pointer = source.buffer.contents().advanced(by: source.offset + index * source.stride)
                return (0..<3).map { pointer.load(fromByteOffset: $0 * 4, as: Float.self) }
            }
            let triangles = (0..<(faces.count * 3)).map { index -> UInt32 in
                let pointer = faces.buffer.contents().advanced(by: index * faces.bytesPerIndex)
                return faces.bytesPerIndex == 2
                    ? UInt32(pointer.load(as: UInt16.self)) : pointer.load(as: UInt32.self)
            }
            let part = Part(id: anchor.identifier, transform: anchor.transform.flattened,
                            vertices: vertices, triangles: triangles)
            return part.isValid ? part : nil
        }
    }

    func makeScene() -> SCNScene {
        let scene = SCNScene()
        for part in parts where part.isValid {
            let positions = stride(from: 0, to: part.vertices.count, by: 3).map {
                SCNVector3(part.vertices[$0], part.vertices[$0 + 1], part.vertices[$0 + 2])
            }
            let source = SCNGeometrySource(vertices: positions)
            let element = SCNGeometryElement(indices: part.triangles, primitiveType: .triangles)
            let geometry = SCNGeometry(sources: [source], elements: [element])
            let material = SCNMaterial()
            material.diffuse.contents = UIColor(white: 0.72, alpha: 1)
            material.isDoubleSided = false
            material.lightingModel = .lambert
            geometry.materials = [material]
            let node = SCNNode(geometry: geometry)
            node.name = part.id.uuidString
            node.simdTransform = part.matrix
            scene.rootNode.addChildNode(node)
        }
        return scene
    }

    func write(to directory: URL) throws {
        guard !parts.isEmpty, parts.allSatisfy(\.isValid) else { throw MeshError.invalidGeometry }
        try JSONEncoder().encode(self).write(to: directory.appendingPathComponent("lidar-mesh.json"), options: .atomic)
    }

    static func load(from directory: URL) throws -> LidarMesh {
        let mesh = try JSONDecoder().decode(Self.self,
            from: Data(contentsOf: directory.appendingPathComponent("lidar-mesh.json")))
        guard !mesh.parts.isEmpty, mesh.parts.allSatisfy(\.isValid) else { throw MeshError.invalidGeometry }
        return mesh
    }

    enum MeshError: Error { case invalidGeometry }
}

private extension LidarMesh.Part {
    var matrix: simd_float4x4 {
        simd_float4x4(columns: (
            SIMD4(transform[0], transform[1], transform[2], transform[3]),
            SIMD4(transform[4], transform[5], transform[6], transform[7]),
            SIMD4(transform[8], transform[9], transform[10], transform[11]),
            SIMD4(transform[12], transform[13], transform[14], transform[15])
        ))
    }
}

@MainActor
final class LidarMeshRecorder {
    private let directory: URL
    private let queue = DispatchQueue(label: "com.standardphysics.lidar", qos: .utility)
    private let peopleFilteringEnabled: Bool
    private var saveTask: Task<Void, Never>?
    private var lastTimestamp: TimeInterval = -.infinity
    private(set) var triangleCount = 0
    private(set) var error: Error?

    init(directory: URL, peopleFilteringEnabled: Bool = false) {
        self.directory = directory
        self.peopleFilteringEnabled = peopleFilteringEnabled
    }

    func sample(_ frame: ARFrame, force: Bool = false) {
        guard saveTask == nil, force || frame.timestamp - lastTimestamp >= 2 else { return }
        let anchors = frame.anchors.compactMap { $0 as? ARMeshAnchor }
        guard force || !anchors.isEmpty else { return }
        let mesh = LidarMesh(anchors: anchors, peopleFilteringEnabled: peopleFilteringEnabled)
        lastTimestamp = frame.timestamp
        let directory = directory
        let queue = queue
        saveTask = Task { [weak self] in
            let result: Result<Void, Error> = await withCheckedContinuation { continuation in
                queue.async { continuation.resume(returning: Result { try mesh.write(to: directory) }) }
            }
            guard let self else { return }
            switch result {
            case .success:
                error = nil
                triangleCount = mesh.triangleCount
            case .failure(let failure): error = failure
            }
            saveTask = nil
        }
    }

    func finish(frame: ARFrame?) async throws {
        await saveTask?.value
        if let frame { sample(frame, force: true) }
        await saveTask?.value
        if let error { throw error }
        guard triangleCount > 0 else { throw LidarMesh.MeshError.invalidGeometry }
    }
}
