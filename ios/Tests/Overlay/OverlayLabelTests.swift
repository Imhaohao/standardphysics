import CoreGraphics
import XCTest
import simd
@testable import StandardPhysics

final class LengthTextTests: XCTestCase {
    func testInchesRoundToTheNearestHalf() {
        XCTAssertEqual(LengthText(meters: 0.8636).inches, "34 in")
        XCTAssertEqual(LengthText(meters: 0.8763).inches, "34½ in")
        XCTAssertEqual(LengthText(meters: 0.8636).centimeters, "86 cm")
    }

    func testNegativeLengthsClampToZero() {
        XCTAssertEqual(LengthText(meters: -0.01), LengthText(meters: 0))
        XCTAssertEqual(LengthText(meters: 0).inches, "0 in")
    }
}

final class LabelLayoutTests: XCTestCase {
    private let bounds = CGRect(x: 0, y: 0, width: 400, height: 800)
    private let size = CGSize(width: 100, height: 30)

    func testSingleLabelSitsAboveItsAnchor() throws {
        let placed = LabelLayout.place([LabelPlacementRequest(id: "a", anchor: CGPoint(x: 200, y: 400), size: size, priority: 0)], in: bounds)
        let frame = try XCTUnwrap(placed.first?.frame)
        XCTAssertEqual(frame.midX, 200)
        XCTAssertLessThan(frame.maxY, 400)
    }

    func testCrowdedLabelsNeverOverlap() {
        let requests = (0..<12).map { index in
            LabelPlacementRequest(id: "\(index)", anchor: CGPoint(x: 200 + CGFloat(index), y: 400), size: size, priority: index % 3)
        }
        let frames = LabelLayout.place(requests, in: bounds).map(\.frame)
        XCTAssertGreaterThan(frames.count, 1)
        for (index, frame) in frames.enumerated() {
            for other in frames[(index + 1)...] {
                XCTAssertFalse(frame.intersects(other), "\(frame) overlaps \(other)")
            }
        }
    }

    func testHigherPriorityWinsTheContestedSpot() throws {
        let anchor = CGPoint(x: 200, y: 400)
        let placed = LabelLayout.place([
            LabelPlacementRequest(id: "low", anchor: anchor, size: size, priority: 1),
            LabelPlacementRequest(id: "high", anchor: anchor, size: size, priority: 30),
        ], in: bounds)
        let high = try XCTUnwrap(placed.first { $0.id == "high" })
        XCTAssertEqual(high.frame, LabelLayout.candidateFrames(for: LabelPlacementRequest(id: "high", anchor: anchor, size: size, priority: 30))[0])
    }

    func testLabelsStayOnScreen() throws {
        let placed = LabelLayout.place([LabelPlacementRequest(id: "edge", anchor: CGPoint(x: 200, y: 5), size: size, priority: 0)], in: bounds)
        let frame = try XCTUnwrap(placed.first?.frame)
        XCTAssertTrue(bounds.contains(frame))
        XCTAssertGreaterThan(frame.minY, 5)
    }
}

final class OverlayLabelBuilderTests: XCTestCase {
    private let measurements = MeasurementEstimator.estimate(from: OverlayFixtures.shop).measurements

    func testFindingStatusTintsTheMatchingMeasurement() throws {
        let labels = OverlayLabelBuilder.labels(
            measurements: measurements,
            findings: [OverlayFixtures.finding("counter-1", .pass), OverlayFixtures.finding("counter-1", .fail)],
            elements: OverlayFixtures.shop
        )
        let counter = try XCTUnwrap(labels.first { $0.id == "topHeight:counter-1" })
        XCTAssertEqual(counter.content.status, .fail)
        XCTAssertEqual(counter.content, .measurement(kind: .topHeight, length: LengthText(meters: 0.96), status: .fail))
        XCTAssertFalse(labels.contains { $0.id == "finding:counter-1" })
    }

    func testUnmeasuredSubjectsGetABadgeOnTop() throws {
        let labels = OverlayLabelBuilder.labels(
            measurements: [],
            findings: [OverlayFixtures.finding("door-1", .needsInfo, section: "11B-404.2.9")],
            elements: OverlayFixtures.shop
        )
        let badge = try XCTUnwrap(labels.first)
        XCTAssertEqual(badge.content, .finding(section: "11B-404.2.9", status: .needsInfo))
        XCTAssertEqual(badge.anchor.y, 2.06, accuracy: 1e-5)
    }

    func testNotApplicableAndUnknownSubjectsAreHidden() {
        let labels = OverlayLabelBuilder.labels(
            measurements: [],
            findings: [OverlayFixtures.finding("door-1", .notApplicable), OverlayFixtures.finding("ghost", .fail)],
            elements: OverlayFixtures.shop
        )
        XCTAssertEqual(labels, [])
    }

    func testProblemsOutrankPlainMeasurements() throws {
        let labels = OverlayLabelBuilder.labels(
            measurements: measurements,
            findings: [OverlayFixtures.finding("table-1", .fail)],
            elements: OverlayFixtures.shop
        )
        let top = try XCTUnwrap(labels.max { $0.priority < $1.priority })
        XCTAssertEqual(top.id, "topHeight:table-1")
    }

    func testChipDescriptionReadsNaturally() {
        let content = OverlayLabelContent.measurement(kind: .clearWidth, length: LengthText(meters: 0.8636), status: .fail)
        XCTAssertEqual(OverlayChipDescription.text(for: content), "Clear width 34 in, 86 cm, likely a problem")
    }
}

final class LabelProjectorTests: XCTestCase {
    @MainActor
    func testLabelsBehindTheCameraAreDropped() {
        let labels = OverlayLabelBuilder.labels(measurements: MeasurementEstimator.estimate(from: OverlayFixtures.shop).measurements, findings: [], elements: [])
        let placed = LabelProjector.place(labels, in: CGRect(x: 0, y: 0, width: 400, height: 800), scale: 1) { point in
            point.x < 0 ? nil : CGPoint(x: 200 + CGFloat(point.x) * 50, y: 400 - CGFloat(point.y) * 100)
        }
        XCTAssertFalse(placed.contains { $0.id == "topHeight:counter-1" })
        XCTAssertTrue(placed.contains { $0.id == "clearWidth:door-1" })
        XCTAssertEqual(placed.first { $0.id == "clearWidth:door-1" }?.span.count, 2)
    }

    @MainActor
    func testStatusIconWidensTheEstimate() {
        let plain = LabelProjector.estimatedSize(of: .measurement(kind: .topHeight, length: LengthText(meters: 0.9), status: nil), scale: 1)
        let flagged = LabelProjector.estimatedSize(of: .measurement(kind: .topHeight, length: LengthText(meters: 0.9), status: .fail), scale: 1)
        XCTAssertGreaterThan(flagged.width, plain.width)
        XCTAssertEqual(LabelProjector.estimatedSize(of: .finding(section: "11B-1", status: .pass), scale: 2).height, OverlayStyle.Label.height * 2)
    }
}
