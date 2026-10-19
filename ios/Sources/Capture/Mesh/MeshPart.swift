import Foundation
import simd

/// One `ARMeshAnchor`, copied out of ARKit's Metal buffers into packed little-endian bytes.
nonisolated struct MeshPart: Sendable, Equatable {
    static let bytesPerVertex = 3 * MemoryLayout<Float>.size
    static let bytesPerFace = 3 * MemoryLayout<UInt32>.size

    let id: UUID
    let transform: simd_float4x4
    /// `Float32 x, y, z` per vertex, in the anchor's local space.
    let vertices: Data
    /// `UInt32 a, b, c` per triangle.
    let indices: Data
    /// One `ARMeshClassification` raw value per triangle.
    let classification: Data?

    var vertexCount: Int { vertices.count / Self.bytesPerVertex }
    var faceCount: Int { indices.count / Self.bytesPerFace }
}

nonisolated struct SPMMesh: Sendable, Equatable {
    var floorY: Float
    var parts: [MeshPart]
}

/// Copies strided geometry buffers into tightly packed `Data` with bulk copies, never per-element boxing.
nonisolated enum GeometryPacking {
    static func packFloat3(_ base: UnsafeRawPointer, count: Int, stride: Int, offset: Int) -> Data {
        pack(base + offset, count: count, stride: stride, elementSize: MeshPart.bytesPerVertex)
    }

    static func packTriangles(_ base: UnsafeRawPointer, faceCount: Int, bytesPerIndex: Int) -> Data {
        let indexCount = faceCount * 3
        if bytesPerIndex == MemoryLayout<UInt32>.size {
            return Data(bytes: base, count: indexCount * bytesPerIndex)
        }
        let narrow = base.bindMemory(to: UInt16.self, capacity: indexCount)
        var wide = Data(count: indexCount * MemoryLayout<UInt32>.size)
        wide.withUnsafeMutableBytes { raw in
            let output = raw.bindMemory(to: UInt32.self)
            for index in 0..<indexCount {
                output[index] = UInt32(narrow[index])
            }
        }
        return wide
    }

    static func packBytes(_ base: UnsafeRawPointer, count: Int, stride: Int, offset: Int) -> Data {
        pack(base + offset, count: count, stride: stride, elementSize: 1)
    }

    private static func pack(_ start: UnsafeRawPointer, count: Int, stride: Int, elementSize: Int) -> Data {
        if stride == elementSize {
            return Data(bytes: start, count: count * elementSize)
        }
        var packed = Data(count: count * elementSize)
        packed.withUnsafeMutableBytes { raw in
            guard let destination = raw.baseAddress else { return }
            for element in 0..<count {
                (destination + element * elementSize).copyMemory(from: start + element * stride, byteCount: elementSize)
            }
        }
        return packed
    }
}

/// Picks the floor height from mesh triangles ARKit classified as floor, falling back to the
/// lowest vertex when nothing is classified.
nonisolated enum FloorEstimator {
    static let floorClassification: UInt8 = 2
    private static let maximumSamples = 100_000

    static func floorY(of parts: [MeshPart]) -> Float {
        let totalFaces = parts.reduce(0) { $0 + $1.faceCount }
        let step = max(1, totalFaces / maximumSamples)
        var heights: [Float] = []
        for part in parts {
            heights.append(contentsOf: floorHeights(in: part, step: step))
        }
        guard !heights.isEmpty else { return lowestVertexY(of: parts, step: step) }
        heights.sort()
        return heights[heights.count / 2]
    }

    private static func floorHeights(in part: MeshPart, step: Int) -> [Float] {
        guard let classification = part.classification else { return [] }
        return part.vertices.withUnsafeBytes { vertexBytes in
            part.indices.withUnsafeBytes { indexBytes in
                classification.withUnsafeBytes { classBytes in
                    let vertices = vertexBytes.bindMemory(to: Float.self)
                    let indices = indexBytes.bindMemory(to: UInt32.self)
                    let classes = classBytes.bindMemory(to: UInt8.self)
                    return Swift.stride(from: 0, to: part.faceCount, by: step).compactMap { face in
                        guard classes[face] == floorClassification else { return nil }
                        return worldY(vertices, Int(indices[face * 3]), part.transform)
                    }
                }
            }
        }
    }

    private static func lowestVertexY(of parts: [MeshPart], step: Int) -> Float {
        var lowest = Float.greatestFiniteMagnitude
        for part in parts {
            part.vertices.withUnsafeBytes { bytes in
                let vertices = bytes.bindMemory(to: Float.self)
                for vertex in Swift.stride(from: 0, to: part.vertexCount, by: step) {
                    lowest = min(lowest, worldY(vertices, vertex, part.transform))
                }
            }
        }
        return lowest == .greatestFiniteMagnitude ? 0 : lowest
    }

    private static func worldY(_ vertices: UnsafeBufferPointer<Float>, _ vertex: Int, _ transform: simd_float4x4) -> Float {
        let local = SIMD4<Float>(vertices[vertex * 3], vertices[vertex * 3 + 1], vertices[vertex * 3 + 2], 1)
        return (transform * local).y
    }
}
