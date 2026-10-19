import XCTest
import simd
@testable import StandardPhysics

final class MeasurementEstimatorTests: XCTestCase {
    private func measurement(_ kind: MeasurementKind, _ subjectID: String, in result: LiveMeasurements) -> LiveMeasurement? {
        result.measurements.first { $0.kind == kind && $0.subjectID == subjectID }
    }

    func testObjectTopHeightsAreMeasuredFromTheFloor() throws {
        let result = MeasurementEstimator.estimate(from: OverlayFixtures.shop)
        XCTAssertEqual(result.floorHeight, 0, accuracy: 1e-5)
        let counter = try XCTUnwrap(measurement(.topHeight, "counter-1", in: result))
        XCTAssertEqual(counter.meters, 0.96, accuracy: 1e-5)
        XCTAssertEqual(counter.anchor.y, 0.96, accuracy: 1e-5)
    }

    func testFloorElementSetsTheReferenceHeight() throws {
        let raised = OverlayFixtures.shop + [
            OverlayFixtures.element("floor", kind: .floor, center: SIMD3(0, 0.2, 0), size: SIMD3(4, 3, 0)),
        ]
        let result = MeasurementEstimator.estimate(from: raised)
        XCTAssertEqual(result.floorHeight, 0.2, accuracy: 1e-5)
        XCTAssertEqual(try XCTUnwrap(measurement(.topHeight, "table-1", in: result)).meters, 0.54, accuracy: 1e-5)
    }

    func testDoorClearWidthSpansTheOpening() throws {
        let door = try XCTUnwrap(measurement(.clearWidth, "door-1", in: MeasurementEstimator.estimate(from: OverlayFixtures.shop)))
        XCTAssertEqual(door.meters, 0.86, accuracy: 1e-5)
        XCTAssertEqual(door.span.count, 2)
        XCTAssertEqual(simd_distance(door.span[0], door.span[1]), 0.86, accuracy: 1e-5)
    }

    func testNarrowestPassageFindsTheTightestWalkableGap() throws {
        let result = MeasurementEstimator.estimate(from: OverlayFixtures.shop)
        let passage = try XCTUnwrap(result.measurements.first { $0.kind == .passageWidth })
        XCTAssertEqual(passage.subjectID, "table-1|wall-north")
        XCTAssertEqual(passage.meters, 0.9, accuracy: 1e-4)
        XCTAssertEqual(passage.anchor.y, 0, accuracy: 1e-5)
        XCTAssertEqual(passage.anchor.z, -1.05, accuracy: 1e-4)
    }

    func testRotatedObjectsUseTheirRealFootprint() throws {
        let elements = [
            OverlayFixtures.element("a", kind: .object, center: SIMD3(0, 0.4, 0), size: SIMD3(1, 0.8, 1), yaw: .pi / 4),
            OverlayFixtures.element("b", kind: .object, center: SIMD3(2, 0.4, 0), size: SIMD3(1, 0.8, 1)),
        ]
        let passage = try XCTUnwrap(MeasurementEstimator.narrowestPassage(in: elements, floorHeight: 0))
        XCTAssertEqual(passage.meters, 2 - 0.5 - sqrt(2) / 2, accuracy: 1e-4)
    }

    func testWallMountedObjectsDoNotNarrowThePassage() {
        let elements = [
            OverlayFixtures.element("tv", kind: .object, center: SIMD3(0, 1.8, -1.3), size: SIMD3(1, 0.6, 0.1)),
            OverlayFixtures.element("wall", kind: .wall, center: SIMD3(0, 1.25, -1.5), size: SIMD3(4, 2.5, 0)),
        ]
        XCTAssertNil(MeasurementEstimator.narrowestPassage(in: elements, floorHeight: 0))
    }

    func testTouchingAndFarApartObjectsAreNotPassages() {
        let elements = [
            OverlayFixtures.element("a", kind: .object, center: SIMD3(0, 0.4, 0), size: SIMD3(1, 0.8, 1)),
            OverlayFixtures.element("b", kind: .object, center: SIMD3(1.02, 0.4, 0), size: SIMD3(1, 0.8, 1)),
            OverlayFixtures.element("c", kind: .object, center: SIMD3(8, 0.4, 0), size: SIMD3(1, 0.8, 1)),
        ]
        XCTAssertNil(MeasurementEstimator.narrowestPassage(in: elements, floorHeight: 0))
    }

    func testPlanCollectsWallsOpeningsAndFootprints() {
        let plan = MeasurementEstimator.estimate(from: OverlayFixtures.shop).plan
        XCTAssertEqual(plan.walls.count, 2)
        XCTAssertEqual(plan.openings.map(\.id), ["door-1"])
        XCTAssertEqual(plan.objects.map(\.category), ["counter", "table"])
        XCTAssertEqual(plan.walls[1].length, 3, accuracy: 1e-5)
    }

    func testEmptySceneHasNoMeasurements() {
        XCTAssertEqual(MeasurementEstimator.estimate(from: []), .empty)
    }
}

final class PlanGeometryTests: XCTestCase {
    func testCrossingSegmentsHaveNoGap() {
        let first = PlanSegment(start: SIMD2(-1, 0), end: SIMD2(1, 0))
        let second = PlanSegment(start: SIMD2(0, -1), end: SIMD2(0, 1))
        XCTAssertEqual(PlanGeometry.closestPoints(first, second).distance, 0, accuracy: 1e-6)
    }

    func testParallelSegmentsMeasureTheirSeparation() {
        let first = PlanSegment(start: SIMD2(0, 0), end: SIMD2(2, 0))
        let second = PlanSegment(start: SIMD2(1, 0.75), end: SIMD2(3, 0.75))
        XCTAssertEqual(PlanGeometry.closestPoints(first, second).distance, 0.75, accuracy: 1e-6)
    }

    func testNestedOutlinesAreNotAGap() {
        let outer = PlanGeometry.edges(of: [SIMD2(-2, -2), SIMD2(2, -2), SIMD2(2, 2), SIMD2(-2, 2)])
        let inner = PlanGeometry.edges(of: [SIMD2(-0.5, -0.5), SIMD2(0.5, -0.5), SIMD2(0.5, 0.5), SIMD2(-0.5, 0.5)])
        XCTAssertNil(PlanGeometry.gap(between: outer, and: inner))
    }
}
