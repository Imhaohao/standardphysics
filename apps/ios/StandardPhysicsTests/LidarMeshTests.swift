import XCTest
import simd
@testable import StandardPhysics

final class LidarMeshTests: XCTestCase {
    func testDetailedGeometrySurvivesDiskAndKeepsItsWorldPosition() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        var transform = matrix_identity_float4x4
        transform.columns.3 = SIMD4(2, 3, 4, 1)
        let id = UUID()
        let mesh = LidarMesh(parts: [.init(id: id, transform: transform.flattened,
            vertices: [0, 0, 0, 0.02, 0, 0, 0, 0.4, 0], triangles: [0, 1, 2])])
        try mesh.write(to: directory)
        let restored = try LidarMesh.load(from: directory)
        XCTAssertEqual(restored.triangleCount, 1)
        let node = try XCTUnwrap(restored.makeScene().rootNode.childNodes.first)
        XCTAssertEqual(node.name, id.uuidString)
        XCTAssertEqual(node.simdPosition, SIMD3(2, 3, 4))
        XCTAssertEqual(node.geometry?.sources(for: .vertex).first?.vectorCount, 3)
    }

    func testInvalidTriangleDoesNotReachRenderer() {
        let mesh = LidarMesh(parts: [.init(id: UUID(), transform: matrix_identity_float4x4.flattened,
            vertices: [0, 0, 0], triangles: [0, 1, 99])])
        XCTAssertEqual(mesh.triangleCount, 0)
        XCTAssertTrue(mesh.makeScene().rootNode.childNodes.isEmpty)
    }
}
