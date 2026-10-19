import XCTest
import simd
@testable import StandardPhysics

final class MeshExportTests: XCTestCase {
    private func floats(_ values: [Float]) -> Data {
        values.withUnsafeBytes { Data($0) }
    }

    private func indices(_ values: [UInt32]) -> Data {
        values.withUnsafeBytes { Data($0) }
    }

    private func translation(_ y: Float) -> simd_float4x4 {
        var matrix = matrix_identity_float4x4
        matrix.columns.3 = SIMD4<Float>(0.5, y, -2, 1)
        return matrix
    }

    private func triangle(id: UUID = UUID(), y: Float, classes: [UInt8]?) -> MeshPart {
        MeshPart(
            id: id,
            transform: translation(y),
            vertices: floats([0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 1]),
            indices: indices([0, 1, 2, 1, 3, 2]),
            classification: classes.map { Data($0) }
        )
    }

    func testRoundTripPreservesEveryField() throws {
        let snapshot = SPMMesh(floorY: -1.25, parts: [triangle(y: -1.25, classes: [2, 1]), triangle(y: 0.4, classes: nil)])
        let encoded = SPMFormat.encode(snapshot)
        XCTAssertEqual(encoded.count, SPMFormat.encodedSize(of: snapshot))
        XCTAssertEqual(encoded.prefix(4), Data("SPM1".utf8))
        XCTAssertEqual(try SPMFormat.decode(encoded), snapshot)
    }

    func testHeaderLayoutIsLittleEndian() {
        let part = triangle(y: 0, classes: [0, 0])
        let encoded = SPMFormat.encode(SPMMesh(floorY: 1, parts: [part]))
        let bytes = [UInt8](encoded)
        XCTAssertEqual(Array(bytes[4..<8]), [1, 0, 0, 0])
        XCTAssertEqual(Array(bytes[8..<12]), [0x00, 0x00, 0x80, 0x3F])
        XCTAssertEqual(Array(bytes[12..<16]), [1, 0, 0, 0])
        XCTAssertEqual(Array(bytes[16..<32]), withUnsafeBytes(of: part.id.uuid) { Array($0) })
        let counts = 32 + 64
        XCTAssertEqual(Array(bytes[counts..<(counts + 9)]), [4, 0, 0, 0, 2, 0, 0, 0, 1])
    }

    func testDecodeRejectsGarbage() {
        XCTAssertThrowsError(try SPMFormat.decode(Data("NOPE0000".utf8))) { XCTAssertEqual($0 as? SPMError, .badMagic) }
        let encoded = SPMFormat.encode(SPMMesh(floorY: 0, parts: [triangle(y: 0, classes: [1, 1])]))
        XCTAssertThrowsError(try SPMFormat.decode(encoded.prefix(encoded.count - 1))) { XCTAssertEqual($0 as? SPMError, .truncated) }
    }

    func testPackingHonoursStrideAndOffset() {
        let interleaved: [Float] = [9, 1, 2, 3, 9, 4, 5, 6, 9, 7, 8, 9, 9]
        let packed = interleaved.withUnsafeBytes {
            GeometryPacking.packFloat3($0.baseAddress!, count: 3, stride: 16, offset: 4)
        }
        XCTAssertEqual(packed, floats([1, 2, 3, 4, 5, 6, 7, 8, 9]))
    }

    func testPackingWidensSixteenBitIndices() {
        let narrow: [UInt16] = [0, 1, 2, 2, 1, 65535]
        let packed = narrow.withUnsafeBytes {
            GeometryPacking.packTriangles($0.baseAddress!, faceCount: 2, bytesPerIndex: 2)
        }
        XCTAssertEqual(packed, indices([0, 1, 2, 2, 1, 65535]))
    }

    func testFloorComesFromFloorClassifiedTriangles() {
        let floor = triangle(y: -1.4, classes: [2, 2])
        let table = triangle(y: -0.7, classes: [4, 4])
        let lowNoise = triangle(y: -3, classes: [0, 0])
        XCTAssertEqual(FloorEstimator.floorY(of: [floor, table, lowNoise]), -1.4, accuracy: 0.0001)
    }

    func testFloorFallsBackToLowestVertex() {
        XCTAssertEqual(FloorEstimator.floorY(of: [triangle(y: -0.2, classes: nil), triangle(y: -0.9, classes: nil)]), -0.9, accuracy: 0.0001)
        XCTAssertEqual(FloorEstimator.floorY(of: []), 0)
    }

    func testEncodeMergesCarriedOverMeshAndPrefersLiveParts() async throws {
        let shared = UUID()
        let carried = SPMFormat.encode(SPMMesh(floorY: 0, parts: [triangle(y: 0, classes: [2, 2]), triangle(id: shared, y: 5, classes: nil)]))
        let live = triangle(id: shared, y: 0, classes: [2, 2])
        let merged = try SPMFormat.decode(await MeshExporter.encode([live], carriedOver: carried))
        XCTAssertEqual(merged.parts.count, 2)
        XCTAssertEqual(merged.parts.last, live)
        let ignoresCorrupt = try SPMFormat.decode(await MeshExporter.encode([live], carriedOver: Data([1, 2, 3])))
        XCTAssertEqual(ignoresCorrupt.parts, [live])
    }

    func testWritingAMillionAndAHalfVerticesIsFast() async throws {
        let parts = (0..<30).map { _ in Self.syntheticPart(vertexCount: 50_000) }
        XCTAssertEqual(parts.reduce(0) { $0 + $1.vertexCount }, 1_500_000)
        let url = FileManager.default.temporaryDirectory.appending(path: "bench-\(UUID().uuidString).spm")
        defer { try? FileManager.default.removeItem(at: url) }

        let clock = ContinuousClock()
        let elapsed = try await clock.measure {
            let data = await MeshExporter.encode(parts, carriedOver: nil)
            try AtomicFileWriter().write(data, to: url)
        }
        let size = try XCTUnwrap(try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int)
        XCTAssertGreaterThan(size, 1_500_000 * 12)
        XCTAssertLessThan(elapsed, .seconds(2), "mesh.spm write took \(elapsed)")
    }

    private static func syntheticPart(vertexCount: Int) -> MeshPart {
        let faceCount = vertexCount * 2
        var vertices = [Float](repeating: 0, count: vertexCount * 3)
        for vertex in 0..<vertexCount {
            vertices[vertex * 3] = Float(vertex % 250) * 0.02
            vertices[vertex * 3 + 2] = Float(vertex / 250) * 0.02
        }
        var faceIndices = [UInt32](repeating: 0, count: faceCount * 3)
        for face in 0..<faceCount {
            let base = UInt32(face / 2)
            faceIndices[face * 3] = base
            faceIndices[face * 3 + 1] = min(base + 1, UInt32(vertexCount - 1))
            faceIndices[face * 3 + 2] = min(base + 250, UInt32(vertexCount - 1))
        }
        return MeshPart(
            id: UUID(),
            transform: matrix_identity_float4x4,
            vertices: vertices.withUnsafeBytes { Data($0) },
            indices: faceIndices.withUnsafeBytes { Data($0) },
            classification: Data(repeating: FloorEstimator.floorClassification, count: faceCount)
        )
    }
}
