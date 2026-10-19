import CoreGraphics
import XCTest
@testable import StandardPhysics

final class DetectorOutputDecoderTests: XCTestCase {
    private let chairID: Int32 = 56
    private let personID: Int32 = 0
    private let tableID: Int32 = 60

    private let decoder = DetectorOutputDecoder(
        labelsByClassID: ClassMapper.cocoLabelsByClassID,
        mapper: .standard,
        minimumConfidence: 0.5
    )

    func testLabelOrderMatchesCocoClassIDs() {
        XCTAssertEqual(ClassMapper.cocoLabelsByClassID.count, 80)
        XCTAssertEqual(ClassMapper.cocoLabelsByClassID[Int(chairID)], "chair")
        XCTAssertEqual(ClassMapper.cocoLabelsByClassID[Int(tableID)], "dining table")
        XCTAssertEqual(ClassMapper.cocoLabelsByClassID[79], "toothbrush")
    }

    func testCenterBoxBecomesTopLeftRect() throws {
        let output = DetectorOutput(scores: [0.9], classIDs: [chairID], boxes: [0.5, 0.4, 0.2, 0.4])
        let detection = try XCTUnwrap(decoder.detections(from: output).first)
        XCTAssertEqual(detection.label, "chair")
        XCTAssertEqual(detection.category, "chair")
        XCTAssertEqual(detection.confidence, 0.9)
        XCTAssertEqual(detection.boundingBox.minX, 0.4, accuracy: 1e-6)
        XCTAssertEqual(detection.boundingBox.minY, 0.2, accuracy: 1e-6)
        XCTAssertEqual(detection.boundingBox.width, 0.2, accuracy: 1e-6)
        XCTAssertEqual(detection.boundingBox.height, 0.4, accuracy: 1e-6)
    }

    func testLowScoresAndUnmappedClassesAreDropped() {
        let output = DetectorOutput(
            scores: [0.3, 0.95, 0.8],
            classIDs: [chairID, personID, tableID],
            boxes: [0.5, 0.5, 0.1, 0.1, 0.5, 0.5, 0.1, 0.1, 0.5, 0.5, 0.1, 0.1]
        )
        XCTAssertEqual(decoder.detections(from: output).map(\.category), ["table"])
    }

    func testResultsAreSortedByConfidence() {
        let output = DetectorOutput(
            scores: [0.6, 0.9],
            classIDs: [chairID, tableID],
            boxes: [0.3, 0.3, 0.1, 0.1, 0.7, 0.7, 0.2, 0.2]
        )
        XCTAssertEqual(decoder.detections(from: output).map(\.label), ["dining table", "chair"])
    }

    func testBoxesAreClampedToTheImage() throws {
        let output = DetectorOutput(scores: [0.9], classIDs: [chairID], boxes: [0.95, 0.05, 0.2, 0.2])
        let box = try XCTUnwrap(decoder.detections(from: output).first?.boundingBox)
        XCTAssertEqual(box.minX, 0.85, accuracy: 1e-6)
        XCTAssertEqual(box.maxX, 1, accuracy: 1e-6)
        XCTAssertEqual(box.minY, 0, accuracy: 1e-6)
        XCTAssertEqual(box.maxY, 0.15, accuracy: 1e-6)
    }

    func testOutOfRangeClassIDsAndEmptyBoxesAreIgnored() {
        let output = DetectorOutput(
            scores: [0.9, 0.9, 0.9],
            classIDs: [80, -1, chairID],
            boxes: [0.5, 0.5, 0.1, 0.1, 0.5, 0.5, 0.1, 0.1, 1.5, 1.5, 0.1, 0.1]
        )
        XCTAssertEqual(decoder.detections(from: output), [])
    }

    func testMismatchedTensorLengthsDecodeToNothing() {
        let output = DetectorOutput(scores: [0.9, 0.9], classIDs: [chairID], boxes: [0.5, 0.5, 0.1, 0.1])
        XCTAssertEqual(decoder.detections(from: output), [])
    }
}
