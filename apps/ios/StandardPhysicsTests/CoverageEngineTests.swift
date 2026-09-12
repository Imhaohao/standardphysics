import XCTest
import simd
@testable import StandardPhysics

final class CoverageEngineTests: XCTestCase {
    func testSurfaceNeedsSeparatedViewsAndEnoughObservedArea() {
        let surfaceID = UUID(uuidString: "38C99F20-2327-4BB7-A435-AFCBBB1C2C73")!
        var engine = CoverageEngine(gridSize: 2)
        let surface = SurfaceSnapshot(
            id: surfaceID,
            width: 2,
            height: 2,
            transform: matrix_identity_float4x4,
            confidence: .high
        )

        engine.update(
            surfaces: [surface],
            camera: .lookingStraightAhead(position: SIMD3<Float>(0, 0, 2))
        )
        XCTAssertFalse(engine.snapshot.surfaces[0].isDone)

        engine.update(
            surfaces: [surface],
            camera: .lookingStraightAhead(position: SIMD3<Float>(1.1, 0, 2))
        )

        let result = engine.snapshot.surfaces[0]
        XCTAssertEqual(result.observedFraction, 1, accuracy: 0.001)
        XCTAssertEqual(result.observedSegments, [true, true])
        XCTAssertEqual(result.viewpointCount, 2)
        XCTAssertTrue(result.isDone)
    }

    func testLowConfidenceSurfaceStaysUnfinished() {
        var engine = CoverageEngine(gridSize: 1)
        let surface = SurfaceSnapshot(
            id: UUID(),
            width: 1,
            height: 1,
            transform: matrix_identity_float4x4,
            confidence: .low
        )

        engine.update(
            surfaces: [surface],
            camera: .lookingStraightAhead(position: SIMD3<Float>(0, 0, 2))
        )
        engine.update(
            surfaces: [surface],
            camera: .lookingStraightAhead(position: SIMD3<Float>(1.1, 0, 2))
        )

        XCTAssertFalse(engine.snapshot.surfaces[0].isDone)
    }

    func testGuidancePointsToTheNearestUnfinishedCell() {
        var engine = CoverageEngine(gridSize: 2)
        let surface = SurfaceSnapshot(
            id: UUID(),
            width: 4,
            height: 2,
            transform: matrix_identity_float4x4,
            confidence: .high
        )
        var cameraTransform = matrix_identity_float4x4
        cameraTransform.columns.3 = SIMD4(-1, 0, 2, 1)
        let camera = CameraObservation(
            transform: cameraTransform,
            intrinsics: simd_float3x3(
                SIMD3(500, 0, 0),
                SIMD3(0, 500, 0),
                SIMD3(375, 375, 1)
            ),
            imageResolution: SIMD2(750, 750)
        )

        engine.update(surfaces: [surface], camera: camera)

        XCTAssertEqual(engine.snapshot.surfaces[0].observedSegments, [true, false])
        XCTAssertEqual(engine.snapshot.unfinishedDirection.radians, .pi / 4, accuracy: 0.001)
    }

    func testThinObservedBandDoesNotFillTheWholeWallOnTheMap() {
        var engine = CoverageEngine(gridSize: 10)
        let surface = SurfaceSnapshot(
            id: UUID(),
            width: 4,
            height: 4,
            transform: matrix_identity_float4x4,
            confidence: .high
        )
        let camera = CameraObservation(
            transform: translatedCamera(x: 0, z: 2),
            intrinsics: simd_float3x3(
                SIMD3(500, 0, 0),
                SIMD3(0, 500, 0),
                SIMD3(1_000, 50, 1)
            ),
            imageResolution: SIMD2(2_000, 100)
        )

        engine.update(surfaces: [surface], camera: camera)

        XCTAssertEqual(engine.snapshot.surfaces[0].observedSegments, Array(repeating: false, count: 10))
    }

    func testBackSideOfSurfaceDoesNotCountAsObserved() {
        var engine = CoverageEngine(gridSize: 1)
        let surface = SurfaceSnapshot(
            id: UUID(),
            width: 1,
            height: 1,
            transform: matrix_identity_float4x4,
            confidence: .high
        )
        var cameraTransform = matrix_identity_float4x4
        cameraTransform.columns.0.x = -1
        cameraTransform.columns.2.z = -1
        cameraTransform.columns.3.z = -2

        engine.update(
            surfaces: [surface],
            camera: CameraObservation(
                transform: cameraTransform,
                intrinsics: simd_float3x3(
                    SIMD3(500, 0, 0),
                    SIMD3(0, 500, 0),
                    SIMD3(500, 500, 1)
                ),
                imageResolution: SIMD2(1_000, 1_000)
            )
        )

        XCTAssertEqual(engine.snapshot.surfaces[0].observedFraction, 0)
    }

    private func translatedCamera(x: Float, z: Float) -> simd_float4x4 {
        var transform = matrix_identity_float4x4
        transform.columns.3 = SIMD4(x, 0, z, 1)
        return transform
    }
}
