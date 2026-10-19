import Foundation
import simd

#if !_endian(little)
#error("mesh.spm copies vertex memory verbatim and assumes a little-endian host")
#endif

/// `mesh.spm`, little-endian:
/// "SPM1", u32 version, f32 floorY, u32 partCount, then per part: 16-byte UUID,
/// 16 f32 column-major transform, u32 vertexCount, u32 faceCount, u8 hasClassification,
/// f32[3 * vertexCount], u32[3 * faceCount], u8[faceCount] when classified.
nonisolated enum SPMFormat {
    static let magic = Data("SPM1".utf8)
    static let version: UInt32 = 1
    private static let headerSize = 16
    private static let partHeaderSize = 16 + 64 + 4 + 4 + 1

    static func encode(_ snapshot: SPMMesh) -> Data {
        var data = Data(capacity: encodedSize(of: snapshot))
        data.append(magic)
        append(version, to: &data)
        append(snapshot.floorY.bitPattern, to: &data)
        append(UInt32(snapshot.parts.count), to: &data)
        for part in snapshot.parts {
            appendPart(part, to: &data)
        }
        return data
    }

    static func decode(_ data: Data) throws -> SPMMesh {
        var reader = SPMReader(data: data)
        guard try reader.bytes(4) == magic else { throw SPMError.badMagic }
        let fileVersion = try reader.uint32()
        guard fileVersion == version else { throw SPMError.unsupportedVersion(fileVersion) }
        let floorY = Float(bitPattern: try reader.uint32())
        let partCount = Int(try reader.uint32())
        var parts: [MeshPart] = []
        parts.reserveCapacity(partCount)
        for _ in 0..<partCount {
            parts.append(try reader.part())
        }
        return SPMMesh(floorY: floorY, parts: parts)
    }

    static func encodedSize(of snapshot: SPMMesh) -> Int {
        snapshot.parts.reduce(headerSize) { size, part in
            size + partHeaderSize + part.vertices.count + part.indices.count + (part.classification?.count ?? 0)
        }
    }

    private static func appendPart(_ part: MeshPart, to data: inout Data) {
        withUnsafeBytes(of: part.id.uuid) { data.append(contentsOf: $0) }
        withUnsafeBytes(of: part.transform) { data.append(contentsOf: $0) }
        append(UInt32(part.vertexCount), to: &data)
        append(UInt32(part.faceCount), to: &data)
        data.append(part.classification == nil ? 0 : 1)
        data.append(part.vertices)
        data.append(part.indices)
        if let classification = part.classification {
            data.append(classification)
        }
    }

    private static func append(_ value: UInt32, to data: inout Data) {
        withUnsafeBytes(of: value.littleEndian) { data.append(contentsOf: $0) }
    }
}

nonisolated enum SPMError: Error, Equatable {
    case badMagic
    case unsupportedVersion(UInt32)
    case truncated
}

private nonisolated struct SPMReader {
    let data: Data
    var offset = 0

    init(data: Data) {
        self.data = data
    }

    mutating func bytes(_ count: Int) throws -> Data {
        guard count >= 0, offset + count <= data.count else { throw SPMError.truncated }
        let start = data.startIndex + offset
        offset += count
        return data.subdata(in: start..<(start + count))
    }

    mutating func uint32() throws -> UInt32 {
        let raw = try bytes(4)
        return raw.withUnsafeBytes { UInt32(littleEndian: $0.loadUnaligned(as: UInt32.self)) }
    }

    mutating func part() throws -> MeshPart {
        let uuid = try bytes(16).withUnsafeBytes { $0.loadUnaligned(as: uuid_t.self) }
        let transform = try bytes(64).withUnsafeBytes { $0.loadUnaligned(as: simd_float4x4.self) }
        let vertexCount = Int(try uint32())
        let faceCount = Int(try uint32())
        let hasClassification = try bytes(1).first == 1
        let vertices = try bytes(vertexCount * MeshPart.bytesPerVertex)
        let indices = try bytes(faceCount * MeshPart.bytesPerFace)
        let classification = hasClassification ? try bytes(faceCount) : nil
        return MeshPart(id: UUID(uuid: uuid), transform: transform, vertices: vertices, indices: indices, classification: classification)
    }
}
