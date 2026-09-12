import XCTest
import simd
@testable import StandardPhysics

final class CoverageEngineTests: XCTestCase {
    func testFloorPlaneUsesItsExplicitUpNormal() {
        var engine = CoverageEngine(gridSize: 1)
        let floor = SurfaceSnapshot(
            id: UUID(),
            width: 2,
            height: 2,
            transform: matrix_identity_float4x4,
            confidence: .high,
            isWall: false,
            shape: .plane(
                width: 2,
                height: 2,
                localU: SIMD3<Float>(1, 0, 0),
                localV: SIMD3<Float>(0, 0, 1),
                localNormal: SIMD3<Float>(0, 1, 0)
            )
        )

        engine.update(surfaces: [floor], camera: downwardCamera(position: SIMD3<Float>(0, 2, 0)))

        XCTAssertEqual(engine.snapshot.surfaces[0].observedFraction, 1, accuracy: 0.001)
    }

    func testFloorFactoryUsesXZWhenYIsTheThinDimension() {
        let shape = RoomCoverage.planeShape(
            dimensions: SIMD3<Float>(4, 0.02, 3),
            transform: matrix_identity_float4x4,
            isFloor: true
        )
        let floor = SurfaceSnapshot(
            id: UUID(),
            width: shape.width,
            height: shape.height,
            transform: matrix_identity_float4x4,
            confidence: .high,
            isWall: false,
            shape: shape.surfaceShape
        )
        var engine = CoverageEngine(gridSize: 1)

        engine.update(surfaces: [floor], camera: downwardCamera(position: SIMD3<Float>(0, 2, 0)))

        XCTAssertEqual(engine.snapshot.surfaces[0].observedFraction, 1, accuracy: 0.001)
    }

    func testFloorFactoryUsesRotatedXYWhenZIsTheThinDimension() {
        let transform = simd_float4x4(
            SIMD4(1, 0, 0, 0),
            SIMD4(0, 0, -1, 0),
            SIMD4(0, 1, 0, 0),
            SIMD4(0, 0, 0, 1)
        )
        let shape = RoomCoverage.planeShape(
            dimensions: SIMD3<Float>(4, 3, 0.02),
            transform: transform,
            isFloor: true
        )
        let floor = SurfaceSnapshot(
            id: UUID(),
            width: shape.width,
            height: shape.height,
            transform: transform,
            confidence: .high,
            isWall: false,
            shape: shape.surfaceShape
        )
        var engine = CoverageEngine(gridSize: 1)

        engine.update(surfaces: [floor], camera: downwardCamera(position: SIMD3<Float>(0, 2, 0)))

        XCTAssertEqual(engine.snapshot.surfaces[0].observedFraction, 1, accuracy: 0.001)
    }

    func testFloorFactoryFlipsARotatedXYNormalTowardWorldUp() {
        let transform = simd_float4x4(
            SIMD4(1, 0, 0, 0),
            SIMD4(0, 0, 1, 0),
            SIMD4(0, -1, 0, 0),
            SIMD4(0, 0, 0, 1)
        )
        let shape = RoomCoverage.planeShape(
            dimensions: SIMD3<Float>(4, 3, 0.02),
            transform: transform,
            isFloor: true
        )
        let floor = SurfaceSnapshot(
            id: UUID(),
            width: shape.width,
            height: shape.height,
            transform: transform,
            confidence: .high,
            isWall: false,
            shape: shape.surfaceShape
        )
        var engine = CoverageEngine(gridSize: 1)

        engine.update(surfaces: [floor], camera: downwardCamera(position: SIMD3<Float>(0, 2, 0)))

        XCTAssertEqual(engine.snapshot.surfaces[0].observedFraction, 1, accuracy: 0.001)
    }

    func testBoxFrontAndTopAreIndependentAreaWeightedFaces() {
        let box = SurfaceSnapshot(
            id: UUID(),
            width: 2,
            height: 2,
            transform: matrix_identity_float4x4,
            confidence: .high,
            isWall: false,
            shape: .box(size: SIMD3<Float>(2, 2, 2)),
            kind: "counter"
        )
        var frontEngine = CoverageEngine(gridSize: 1)
        var topEngine = CoverageEngine(gridSize: 1)

        frontEngine.update(surfaces: [box], camera: .lookingStraightAhead(position: SIMD3<Float>(0, 0, 5)))
        topEngine.update(surfaces: [box], camera: .lookingStraightAhead(position: SIMD3<Float>(0, 0, 5)))
        topEngine.update(surfaces: [box], camera: downwardCamera(position: SIMD3<Float>(0, 5, 0)))

        XCTAssertEqual(frontEngine.snapshot.surfaces[0].observedFraction, 1.0 / 6.0, accuracy: 0.001)
        XCTAssertEqual(topEngine.snapshot.surfaces[0].observedFraction, 1.0 / 3.0, accuracy: 0.001)
    }

    func testFiveMeterBoundaryCountsButAFartherViewDoesNot() {
        let surface = standardSurface()
        var boundaryEngine = CoverageEngine(gridSize: 1)
        var distantEngine = CoverageEngine(gridSize: 1)

        boundaryEngine.update(surfaces: [surface], camera: .lookingStraightAhead(position: SIMD3<Float>(0, 0, 5)))
        distantEngine.update(surfaces: [surface], camera: .lookingStraightAhead(position: SIMD3<Float>(0, 0, 5.01)))

        XCTAssertEqual(boundaryEngine.snapshot.surfaces[0].observedFraction, 1, accuracy: 0.001)
        XCTAssertEqual(distantEngine.snapshot.surfaces[0].observedFraction, 0, accuracy: 0.001)
    }

    func testViewAtSixtyDegreesOrMoreDoesNotCount() {
        let surface = standardSurface()
        var acceptableEngine = CoverageEngine(gridSize: 1)
        var exactEngine = CoverageEngine(gridSize: 1)
        var steepEngine = CoverageEngine(gridSize: 1)

        acceptableEngine.update(surfaces: [surface], camera: wideCamera(position: SIMD3<Float>(1.7, 0, 1)))
        exactEngine.update(surfaces: [surface], camera: wideCamera(position: SIMD3<Float>(Float(3).squareRoot(), 0, 1)))
        steepEngine.update(surfaces: [surface], camera: wideCamera(position: SIMD3<Float>(1.75, 0, 1)))

        XCTAssertEqual(acceptableEngine.snapshot.surfaces[0].observedFraction, 1, accuracy: 0.001)
        XCTAssertEqual(exactEngine.snapshot.surfaces[0].observedFraction, 0, accuracy: 0.001)
        XCTAssertEqual(steepEngine.snapshot.surfaces[0].observedFraction, 0, accuracy: 0.001)
    }

    func testAVisibleFacingPointOutsideTheCameraFrustumDoesNotCount() {
        var transform = matrix_identity_float4x4
        transform.columns.3 = SIMD4(3, 0, 0, 1)
        let surface = SurfaceSnapshot(
            id: UUID(),
            width: 1,
            height: 1,
            transform: transform,
            confidence: .high
        )
        var engine = CoverageEngine(gridSize: 1)

        engine.update(surfaces: [surface], camera: .lookingStraightAhead(position: SIMD3<Float>(0, 0, 2)))

        XCTAssertEqual(engine.snapshot.surfaces[0].observedFraction, 0, accuracy: 0.001)
    }

    func testViewsCloserThanOneMeterDoNotAddASecondViewpoint() {
        let surface = standardSurface()
        var engine = CoverageEngine(gridSize: 1)

        engine.update(surfaces: [surface], camera: .lookingStraightAhead(position: SIMD3<Float>(0, 0, 2)))
        engine.update(surfaces: [surface], camera: .lookingStraightAhead(position: SIMD3<Float>(0.99, 0, 2)))

        XCTAssertEqual(engine.snapshot.surfaces[0].viewpointCount, 1)
        XCTAssertFalse(engine.snapshot.surfaces[0].isDone)
    }

    func testFinalReconciliationPreservesOnlyMatchingIDsAndStartsUnknownIDsAtZero() {
        let observedID = UUID()
        let unknownID = UUID()
        let observed = standardSurface(id: observedID)
        let unknown = standardSurface(id: unknownID)
        var engine = CoverageEngine(gridSize: 1)

        engine.update(surfaces: [observed], camera: .lookingStraightAhead(position: SIMD3<Float>(0, 0, 2)))
        engine.update(surfaces: [observed], camera: .lookingStraightAhead(position: SIMD3<Float>(1.1, 0, 2)))
        let reconciled = engine.reconcile(finalSurfaces: [observed, unknown])

        XCTAssertEqual(reconciled.surfaces.map(\.id), [observedID, unknownID])
        XCTAssertEqual(reconciled.surfaces[0].observedFraction, 1, accuracy: 0.001)
        XCTAssertEqual(reconciled.surfaces[0].viewpointCount, 2)
        XCTAssertEqual(reconciled.surfaces[1].observedFraction, 0, accuracy: 0.001)
        XCTAssertEqual(reconciled.surfaces[1].viewpointCount, 0)

        let afterDeletion = engine.reconcile(finalSurfaces: [unknown])
        XCTAssertEqual(afterDeletion.surfaces.map(\.id), [unknownID])
    }

    func testFinalReconciliationDoesNotCarryGridCellsAcrossChangedGeometry() {
        let id = UUID()
        let live = standardSurface(id: id)
        var finalTransform = matrix_identity_float4x4
        finalTransform.columns.3 = SIMD4(3, 0, 0, 1)
        let final = SurfaceSnapshot(
            id: id,
            width: 1,
            height: 1,
            transform: finalTransform,
            confidence: .high
        )
        var engine = CoverageEngine(gridSize: 1)

        engine.update(surfaces: [live], camera: .lookingStraightAhead(position: SIMD3<Float>(0, 0, 2)))
        let reconciled = engine.reconcile(finalSurfaces: [final])

        XCTAssertEqual(reconciled.surfaces[0].observedFraction, 0, accuracy: 0.001)
        XCTAssertEqual(reconciled.surfaces[0].viewpointCount, 0)
    }

    func testLiveGeometryChangeReplaysCoverageInsteadOfReusingGridIndices() {
        let id = UUID()
        let live = standardSurface(id: id)
        var movedTransform = matrix_identity_float4x4
        movedTransform.columns.3 = SIMD4(3, 0, 0, 1)
        let moved = SurfaceSnapshot(
            id: id,
            width: 1,
            height: 1,
            transform: movedTransform,
            confidence: .high
        )
        var engine = CoverageEngine(gridSize: 1)
        let camera = CameraObservation.lookingStraightAhead(position: SIMD3<Float>(0, 0, 2))

        engine.update(surfaces: [live], camera: camera)
        engine.update(surfaces: [moved], camera: camera)

        XCTAssertEqual(engine.snapshot.surfaces[0].observedFraction, 0, accuracy: 0.001)
        XCTAssertEqual(engine.snapshot.surfaces[0].viewpointCount, 0)
    }

    func testInstructionNamesTheNearestUnfinishedRegion() {
        var nearbyTransform = matrix_identity_float4x4
        nearbyTransform.columns.3 = SIMD4(0, 0, -2, 1)
        var distantTransform = matrix_identity_float4x4
        distantTransform.columns.3 = SIMD4(0, 0, -4, 1)
        let nearby = SurfaceSnapshot(id: UUID(), width: 1, height: 1, transform: nearbyTransform, confidence: .high, kind: "wall", name: "back wall")
        let distant = SurfaceSnapshot(id: UUID(), width: 1, height: 1, transform: distantTransform, confidence: .high, isWall: false, kind: "counter")
        var engine = CoverageEngine(gridSize: 1)

        engine.update(surfaces: [distant, nearby], camera: .lookingStraightAhead(position: .zero))

        XCTAssertEqual(engine.snapshot.instruction, "Point the phone at the back wall.")
    }

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

    private func standardSurface(id: UUID = UUID()) -> SurfaceSnapshot {
        SurfaceSnapshot(
            id: id,
            width: 1,
            height: 1,
            transform: matrix_identity_float4x4,
            confidence: .high
        )
    }

    private func wideCamera(position: SIMD3<Float>) -> CameraObservation {
        let camera = CameraObservation.lookingStraightAhead(position: position)
        return CameraObservation(
            transform: camera.transform,
            intrinsics: simd_float3x3(
                SIMD3(100, 0, 0),
                SIMD3(0, 100, 0),
                SIMD3(500, 500, 1)
            ),
            imageResolution: camera.imageResolution
        )
    }

    private func downwardCamera(position: SIMD3<Float>) -> CameraObservation {
        let transform = simd_float4x4(
            SIMD4(1, 0, 0, 0),
            SIMD4(0, 0, -1, 0),
            SIMD4(0, 1, 0, 0),
            SIMD4(position, 1)
        )
        return CameraObservation(
            transform: transform,
            intrinsics: simd_float3x3(
                SIMD3(500, 0, 0),
                SIMD3(0, 500, 0),
                SIMD3(500, 500, 1)
            ),
            imageResolution: SIMD2(1_000, 1_000)
        )
    }
}
