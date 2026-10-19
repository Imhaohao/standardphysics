import CoreGraphics
import XCTest
import simd
@testable import StandardPhysics

final class SceneShapeBuilderTests: XCTestCase {
    private func detection(_ category: String, at center: SIMD3<Float>?) -> Detection {
        Detection(
            label: category,
            category: category,
            confidence: 0.8,
            boundingBox: CGRect(x: 0.4, y: 0.4, width: 0.2, height: 0.2),
            worldCenter: center,
            worldSize: center.map { _ in SIMD3(0.5, 0.9, 0.5) }
        )
    }

    func testElementsMapToStylesAndFloorsAreSkipped() {
        let floor = OverlayFixtures.element("floor", kind: .floor, center: .zero, size: SIMD3(4, 3, 0))
        let shapes = SceneShapeBuilder.shapes(elements: OverlayFixtures.shop + [floor], detections: [])
        XCTAssertEqual(shapes.map(\.style), [.wall, .wall, .opening, .object, .object])
    }

    func testDetectionsOfAlreadyKnownObjectsAreHidden() {
        let shapes = SceneShapeBuilder.shapes(
            elements: OverlayFixtures.shop,
            detections: [
                detection("table", at: SIMD3(0.55, 0.4, -0.25)),
                detection("chair", at: SIMD3(1.5, 0.45, 0.5)),
                detection("chair", at: nil),
            ]
        )
        let detected = shapes.filter { $0.style == .detectedObject }
        XCTAssertEqual(detected.count, 1)
        XCTAssertEqual(detected.first?.transform.columns.3, SIMD4(1.5, 0.45, 0.5, 1))
    }

    func testDetectionIDsSurviveSmallJitter() {
        let first = SceneShapeBuilder.shape(for: detection("chair", at: SIMD3(1.5, 0.45, 0.5)))
        let jittered = SceneShapeBuilder.shape(for: detection("chair", at: SIMD3(1.52, 0.44, 0.49)))
        XCTAssertEqual(first?.id, jittered?.id)
    }

    func testDuplicateIDsAreDropped() {
        let shapes = SceneShapeBuilder.shapes(elements: [], detections: [
            detection("chair", at: SIMD3(1.5, 0.45, 0.5)),
            detection("chair", at: SIMD3(1.51, 0.45, 0.5)),
        ])
        XCTAssertEqual(shapes.count, 1)
    }
}

final class EdgeLayoutTests: XCTestCase {
    func testBoxHasTwelveEdgesOnItsSurface() {
        let size = SIMD3<Float>(1, 2, 3)
        let strokes = EdgeLayout.strokes(dimensions: size, isPlanar: false, isDashed: false)
        XCTAssertEqual(strokes.count, 12)
        XCTAssertEqual(strokes.filter { $0.axis == 1 }.map(\.length), [2, 2, 2, 2])
        XCTAssertTrue(strokes.allSatisfy { stroke in
            (0..<3).filter { $0 != stroke.axis }.allSatisfy { abs(abs(stroke.center[$0]) - size[$0] / 2) < 1e-6 }
        })
    }

    func testPlanarRectangleHasFourEdges() {
        let strokes = EdgeLayout.strokes(dimensions: SIMD3(4, 2.5, 0), isPlanar: true, isDashed: false)
        XCTAssertEqual(strokes.count, 4)
        XCTAssertEqual(Set(strokes.map(\.length)), [4, 2.5])
    }

    func testDashesSplitEachEdgeWithGaps() {
        let edge = EdgeStroke(center: .zero, length: 7, axis: 0)
        let dashes = EdgeLayout.dashes(along: edge, count: 4)
        XCTAssertEqual(dashes.map(\.length), [1, 1, 1, 1])
        XCTAssertEqual(dashes.map(\.center.x), [-3, -1, 1, 3])
        XCTAssertEqual(EdgeLayout.strokes(dimensions: SIMD3(1, 1, 1), isPlanar: false, isDashed: true).count, 12 * EdgeLayout.dashesPerEdge)
    }
}

final class MeshClassificationGrouperTests: XCTestCase {
    func testTrianglesGroupBySurfaceClass() {
        let mesh = MeshSnapshot(
            triangleIndices: [0, 1, 2, 2, 3, 0, 4, 5, 6, 6, 7, 4],
            triangleSurfaces: [MeshSurface.floor.rawValue, MeshSurface.floor.rawValue, MeshSurface.ceiling.rawValue, MeshSurface.door.rawValue]
        )
        let groups = MeshClassificationGrouper.indicesBySurface(mesh, tinted: [.floor, .door])
        XCTAssertEqual(groups[.floor], [0, 1, 2, 2, 3, 0])
        XCTAssertEqual(groups[.door], [6, 7, 4])
        XCTAssertNil(groups[.ceiling])
    }

    func testUnclassifiedMeshFallsBackToNone() {
        let mesh = MeshSnapshot(triangleIndices: [0, 1, 2], triangleSurfaces: [])
        XCTAssertEqual(MeshClassificationGrouper.indicesBySurface(mesh, tinted: [.none]), [.none: [0, 1, 2]])
        XCTAssertEqual(MeshClassificationGrouper.indicesBySurface(mesh, tinted: [.floor]), [:])
    }

    @MainActor
    func testEveryVisibleSurfaceHasAPaletteTint() {
        let untinted = MeshSurface.allCases.filter { OverlayStyle.meshTint(for: $0) == nil }
        XCTAssertEqual(untinted, [.ceiling])
        XCTAssertTrue(MeshSurface.allCases.compactMap(OverlayStyle.meshTint(for:)).allSatisfy { $0.opacity <= 0.3 })
    }
}

final class LiveSceneModelTests: XCTestCase {
    @MainActor
    func testUpdateDerivesShapesMeasurementsAndLabels() {
        let model = LiveSceneModel()
        model.update(elements: OverlayFixtures.shop, detections: [], findings: [OverlayFixtures.finding("door-1", .fail)])
        XCTAssertEqual(model.shapes.count, 5)
        XCTAssertEqual(model.measurements.measurements.count, 4)
        XCTAssertEqual(model.labels.first { $0.id == "clearWidth:door-1" }?.content.status, .fail)
    }

    @MainActor
    func testFindingsAloneRefreshLabelsWithoutRebuildingShapes() {
        let model = LiveSceneModel()
        model.update(elements: OverlayFixtures.shop, detections: [], findings: [])
        let shapes = model.shapes
        model.update(elements: OverlayFixtures.shop, detections: [], findings: [OverlayFixtures.finding("table-1", .needsInfo)])
        XCTAssertEqual(model.shapes, shapes)
        XCTAssertEqual(model.labels.first { $0.id == "topHeight:table-1" }?.content.status, .needsInfo)
    }
}
