import XCTest
import RoomPlan
import simd
@testable import StandardPhysics

final class CoverageViewRulesTests: CoverageEngineTestCase {
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
        var justOverEngine = CoverageEngine(gridSize: 1)
        var steepEngine = CoverageEngine(gridSize: 1)

        acceptableEngine.update(surfaces: [surface], camera: wideCamera(position: SIMD3<Float>(1.72, 0, 1)))
        justOverEngine.update(surfaces: [surface], camera: wideCamera(position: SIMD3<Float>(1.74, 0, 1)))
        steepEngine.update(surfaces: [surface], camera: wideCamera(position: SIMD3<Float>(1.9, 0, 1)))

        XCTAssertEqual(acceptableEngine.snapshot.surfaces[0].observedFraction, 1, accuracy: 0.001)
        XCTAssertEqual(justOverEngine.snapshot.surfaces[0].observedFraction, 0, accuracy: 0.001)
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
}

final class PaintProjectionTests: XCTestCase {
    /// Sees down -z like an AR camera: x and y pass through, w is the distance in front.
    private let lookingDownMinusZ = simd_float4x4(columns: (
        SIMD4<Float>(1, 0, 0, 0),
        SIMD4<Float>(0, 1, 0, 0),
        SIMD4<Float>(0, 0, 0, -1),
        SIMD4<Float>(0, 0, 0, 0)
    ))
    private let screen = CGSize(width: 400, height: 800)

    private var projection: PaintProjection { PaintProjection(worldToClip: lookingDownMinusZ, viewport: screen) }

    func testAPointStraightAheadLandsInTheMiddleOfTheScreen() {
        XCTAssertEqual(projection.screenPoint(of: SIMD3(0, 0, -2)), CGPoint(x: 200, y: 400))
    }

    func testAPointToTheRightLandsRightOfCenterAndShrinksWithDistance() {
        XCTAssertEqual(projection.screenPoint(of: SIMD3(1, 0, -2)), CGPoint(x: 300, y: 400))
        XCTAssertEqual(projection.screenPoint(of: SIMD3(1, 0, -4)), CGPoint(x: 250, y: 400))
    }

    func testAPointBehindTheCameraHasNoPlaceOnScreen() {
        XCTAssertNil(projection.screenPoint(of: SIMD3(0, 0, 1)))
    }

    func testACellIsDrawnOnlyWhenEveryCornerIsInFrontOfTheCamera() {
        let ahead = PaintCell(PaintedSample(worldPoint: SIMD3(0, 0, -2), worldNormal: SIMD3(0, 0, 1), isObserved: true))
        let straddling = PaintCell(PaintedSample(worldPoint: SIMD3(0, 0, 0), worldNormal: SIMD3(1, 0, 0), isObserved: true))

        XCTAssertFalse(projection.path(for: [ahead]).isEmpty)
        XCTAssertTrue(projection.path(for: [straddling]).isEmpty)
    }

    func testACellIsAHandWideSquareLyingOnItsSurface() {
        let cell = PaintCell(PaintedSample(worldPoint: SIMD3(0, 0, 0), worldNormal: SIMD3(0, 0, 1), isObserved: true))
        let half = PaintCell.side / 2

        XCTAssertEqual(cell.corners.count, 4)
        for (corner, expected) in zip(cell.corners, [SIMD3(-half, -half, 0), SIMD3(half, -half, 0), SIMD3(half, half, 0), SIMD3(-half, half, 0)]) {
            XCTAssertEqual(corner.x, expected.x, accuracy: 0.0001)
            XCTAssertEqual(corner.y, expected.y, accuracy: 0.0001)
            XCTAssertEqual(corner.z, expected.z, accuracy: 0.0001)
        }
    }
}
