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

    func testEmptyFinalSnapshotPreservesTheLastSavedGeometry() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let mesh = LidarMesh(parts: [.init(id: UUID(), transform: matrix_identity_float4x4.flattened,
            vertices: [0, 0, 0, 1, 0, 0, 0, 1, 0], triangles: [0, 1, 2])])
        try mesh.write(to: directory)

        XCTAssertThrowsError(try LidarMesh(parts: []).write(to: directory))
        XCTAssertEqual(try LidarMesh.load(from: directory).parts[0].id, mesh.parts[0].id)
    }

    func testRenamingLegacyScanAddsMeasuredMeshWithoutLosingCaptureIdentity() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let room = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "apple_bedroom3.room", withExtension: "json"))
        try FileManager.default.copyItem(at: room, to: directory.appendingPathComponent("room.json"))
        let mesh = LidarMesh(parts: [.init(id: UUID(), transform: matrix_identity_float4x4.flattened,
            vertices: [0, 0, 0, 1, 0, 0, 0, 1, 0], triangles: [0, 1, 2])])
        try mesh.write(to: directory)
        let scan = CapturedScan(id: UUID(), directory: directory, roomURL: directory.appendingPathComponent("room.usdz"),
            duration: 30, artifacts: [], name: "Original", captureNotice: "Scan the back wall again.")

        let updated = try scan.renamed("New name")
        XCTAssertEqual(updated.id, scan.id)
        XCTAssertEqual(updated.name, "New name")
        XCTAssertEqual(updated.captureNotice, scan.captureNotice)
        XCTAssertEqual(updated.artifacts.map(\.kind), [.lidarMesh])
        XCTAssertNotNil(try LidarMesh.load(from: directory).floorY)
        XCTAssertNil(try LidarMesh.load(from: directory).peopleFilteringEnabled)
        let bytes = try Data(contentsOf: updated.artifacts[0].fileURL)
        XCTAssertEqual(try updated.renamed("Again").artifacts.count, 1)
        XCTAssertEqual(try Data(contentsOf: updated.artifacts[0].fileURL), bytes)
    }

    func testLegacyCaptureNeverClaimsPeopleWereFiltered() throws {
        let mesh = LidarMesh(parts: [.init(id: UUID(), transform: matrix_identity_float4x4.flattened,
            vertices: [0, 0, 0, 1, 0, 0, 0, 1, 0], triangles: [0, 1, 2])])
        let data = try JSONEncoder().encode(mesh)
        let decoded = try JSONDecoder().decode(LidarMesh.self, from: data)
        XCTAssertNil(decoded.peopleFilteringEnabled)
        var filtered = decoded
        filtered.peopleFilteringEnabled = true
        filtered.floorY = -1.5
        let restored = try JSONDecoder().decode(LidarMesh.self, from: JSONEncoder().encode(filtered))
        XCTAssertEqual(restored.peopleFilteringEnabled, true)
        XCTAssertEqual(restored.floorY, -1.5)
        XCTAssertEqual(restored.parts[0].vertices, mesh.parts[0].vertices)
    }
}
