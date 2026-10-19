import CoreGraphics
import XCTest
import simd
@testable import StandardPhysics

final class DepthLifterTests: XCTestCase {
    private let camera = CameraGeometry(
        intrinsics: simd_float3x3(columns: (SIMD3(100, 0, 0), SIMD3(0, 100, 0), SIMD3(50, 50, 1))),
        imageSize: SIMD2(100, 100),
        cameraToWorld: matrix_identity_float4x4
    )

    private func uniformDepth(_ meters: Float, confidence: UInt8 = 2, side: Int = 40) -> DepthSamples {
        DepthSamples(
            width: side,
            height: side,
            depths: Array(repeating: meters, count: side * side),
            confidences: Array(repeating: confidence, count: side * side)
        )
    }

    func testCenteredBoxLiftsStraightAhead() throws {
        let box = CGRect(x: 0.4, y: 0.4, width: 0.2, height: 0.2)
        let lifted = try XCTUnwrap(DepthLifter.lift(boundingBox: box, depth: uniformDepth(2), camera: camera))
        XCTAssertEqual(lifted.center.x, 0, accuracy: 1e-4)
        XCTAssertEqual(lifted.center.y, 0, accuracy: 1e-4)
        XCTAssertEqual(lifted.center.z, -2, accuracy: 1e-4)
        XCTAssertEqual(lifted.size.x, 0.4, accuracy: 1e-4)
        XCTAssertEqual(lifted.size.y, 0.4, accuracy: 1e-4)
        XCTAssertEqual(lifted.size.z, DepthLifter.minimumDepthExtent, accuracy: 1e-4)
    }

    func testImageRightAndDownMapToCameraRightAndDown() throws {
        let box = CGRect(x: 0.65, y: 0.65, width: 0.2, height: 0.2)
        let lifted = try XCTUnwrap(DepthLifter.lift(boundingBox: box, depth: uniformDepth(2), camera: camera))
        XCTAssertEqual(lifted.center.x, 0.5, accuracy: 1e-4)
        XCTAssertEqual(lifted.center.y, -0.5, accuracy: 1e-4)
    }

    func testCameraTransformMovesTheResultIntoTheWorld() throws {
        var moved = matrix_identity_float4x4
        moved.columns.3 = SIMD4(1, 1.5, 0, 1)
        let shifted = CameraGeometry(intrinsics: camera.intrinsics, imageSize: camera.imageSize, cameraToWorld: moved)
        let box = CGRect(x: 0.4, y: 0.4, width: 0.2, height: 0.2)
        let lifted = try XCTUnwrap(DepthLifter.lift(boundingBox: box, depth: uniformDepth(3), camera: shifted))
        XCTAssertEqual(lifted.center, SIMD3(1, 1.5, -3))
    }

    func testMedianIgnoresOutliersInTheInnerRegion() throws {
        var depths = Array(repeating: Float(2), count: 100)
        depths[44] = 9
        depths[55] = 0.1
        let samples = DepthSamples(width: 10, height: 10, depths: depths, confidences: nil)
        let box = CGRect(x: 0.2, y: 0.2, width: 0.6, height: 0.6)
        let lifted = try XCTUnwrap(DepthLifter.lift(boundingBox: box, depth: samples, camera: camera))
        XCTAssertEqual(lifted.center.z, -2, accuracy: 1e-4)
    }

    func testLowConfidenceDepthIsRejected() {
        let box = CGRect(x: 0.4, y: 0.4, width: 0.2, height: 0.2)
        XCTAssertNil(DepthLifter.lift(boundingBox: box, depth: uniformDepth(2, confidence: 0), camera: camera))
    }

    func testBoxOutsideTheImageIsRejected() {
        let box = CGRect(x: 1.2, y: 0.4, width: 0.2, height: 0.2)
        XCTAssertNil(DepthLifter.lift(boundingBox: box, depth: uniformDepth(2), camera: camera))
    }

    func testDepthSpreadMeasuresTheObjectsDepth() throws {
        let depths = (0..<100).map { index in Float(2) + Float(index % 10) * 0.1 }
        let samples = DepthSamples(width: 10, height: 10, depths: depths, confidences: nil)
        let lifted = try XCTUnwrap(DepthLifter.lift(boundingBox: CGRect(x: 0, y: 0, width: 1, height: 1), depth: samples, camera: camera))
        XCTAssertEqual(lifted.size.z, 0.9, accuracy: 0.11)
    }

    func testMalformedBufferIsRejectedInsteadOfCrashing() {
        let samples = DepthSamples(width: 10, height: 10, depths: [2, 2], confidences: nil)
        XCTAssertNil(DepthLifter.lift(boundingBox: CGRect(x: 0, y: 0, width: 1, height: 1), depth: samples, camera: camera))
    }
}
