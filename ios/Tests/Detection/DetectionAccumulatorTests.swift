import CoreGraphics
import XCTest
import simd
@testable import StandardPhysics

func liftedDetection(
    _ category: String, at center: SIMD3<Float>, size: SIMD3<Float> = SIMD3(0.6, 1.7, 0.6), confidence: Float = 0.8
) -> Detection {
    Detection(label: category, category: category, confidence: confidence, boundingBox: .zero, worldCenter: center, worldSize: size)
}

final class DetectionAccumulatorTests: XCTestCase {
    private let fridge = SIMD3<Float>(1, 0.85, 2)

    private func accumulate(_ batches: [[Detection]], configuration: DetectionAccumulator.Configuration = .init()) -> DetectionAccumulator {
        batches.reduce(DetectionAccumulator(configuration: configuration)) { $0.adding($1) }
    }

    func testRepeatedSightingsFuseIntoOneTrackWithTheMeanBox() throws {
        let accumulator = accumulate([
            [liftedDetection("refrigerator", at: fridge + SIMD3(0.1, 0, 0), size: SIMD3(0.6, 1.6, 0.6))],
            [liftedDetection("refrigerator", at: fridge - SIMD3(0.1, 0, 0), size: SIMD3(0.8, 1.8, 0.6))],
            [liftedDetection("refrigerator", at: fridge, size: SIMD3(0.7, 1.7, 0.6))],
        ])
        XCTAssertEqual(accumulator.tracks.count, 1)
        let track = try XCTUnwrap(accumulator.confirmed.first)
        XCTAssertEqual(track.hits, 3)
        XCTAssertEqual(simd_distance(track.center, fridge), 0, accuracy: 1e-5)
        XCTAssertEqual(track.size.y, 1.7, accuracy: 1e-5)
    }

    func testATrackNeedsThreeSightingsAndEnoughConfidence() {
        let twice = accumulate(Array(repeating: [liftedDetection("refrigerator", at: fridge)], count: 2))
        XCTAssertTrue(twice.confirmed.isEmpty)

        let doubtful = accumulate(Array(repeating: [liftedDetection("refrigerator", at: fridge, confidence: 0.42)], count: 5))
        XCTAssertEqual(doubtful.tracks.first?.hits, 5)
        XCTAssertTrue(doubtful.confirmed.isEmpty)
    }

    func testDifferentCategoriesAndDistantBoxesStayApart() {
        let accumulator = accumulate([
            [liftedDetection("refrigerator", at: fridge), liftedDetection("oven", at: fridge)],
            [liftedDetection("refrigerator", at: fridge + SIMD3(2, 0, 0))],
        ])
        XCTAssertEqual(accumulator.tracks.map(\.category), ["refrigerator", "oven", "refrigerator"])
    }

    func testLargeObjectsMergeOverAWiderRadius() {
        let sofa = SIMD3<Float>(0, 0.4, 0)
        let wide = SIMD3<Float>(2.0, 0.8, 0.9)
        let accumulator = accumulate([
            [liftedDetection("sofa", at: sofa, size: wide)],
            [liftedDetection("sofa", at: sofa + SIMD3(0.7, 0, 0), size: wide)],
        ])
        XCTAssertEqual(accumulator.tracks.count, 1)
        XCTAssertEqual(accumulator.mergeRadius(of: accumulator.tracks[0]), 1.0, accuracy: 1e-5)

        let small = accumulate([
            [liftedDetection("chair", at: sofa, size: SIMD3(0.5, 0.9, 0.5))],
            [liftedDetection("chair", at: sofa + SIMD3(0.5, 0, 0), size: SIMD3(0.5, 0.9, 0.5))],
        ])
        XCTAssertEqual(small.tracks.count, 2)
    }

    func testOneFrameCannotConfirmATrackWithDuplicateBoxes() {
        let accumulator = accumulate([Array(repeating: liftedDetection("refrigerator", at: fridge), count: 3)])
        XCTAssertTrue(accumulator.confirmed.isEmpty)
        XCTAssertEqual(accumulator.tracks.map(\.hits), [1, 1, 1])
    }

    func testOnlyEngineCategoriesWithAWorldBoxAreKept() {
        let unlifted = Detection(label: "sink", category: "sink", confidence: 0.9, boundingBox: .zero, worldCenter: nil, worldSize: nil)
        let accumulator = accumulate([[liftedDetection(ClassMapper.obstacle, at: fridge), unlifted]])
        XCTAssertTrue(accumulator.tracks.isEmpty)
    }

    func testTheCapEvictsTheLeastSeenUnconfirmedTrack() {
        var configuration = DetectionAccumulator.Configuration()
        configuration.maximumTracks = 2
        let far = SIMD3<Float>(5, 0.5, 5)
        let accumulator = accumulate([
            [liftedDetection("refrigerator", at: fridge), liftedDetection("oven", at: far)],
            [liftedDetection("refrigerator", at: fridge)],
            [liftedDetection("refrigerator", at: fridge)],
            [liftedDetection("sink", at: -far)],
        ], configuration: configuration)
        XCTAssertEqual(accumulator.tracks.map(\.category), ["refrigerator", "sink"])

        let full = accumulate([
            [liftedDetection("refrigerator", at: fridge), liftedDetection("oven", at: far)],
            [liftedDetection("refrigerator", at: fridge), liftedDetection("oven", at: far)],
            [liftedDetection("refrigerator", at: fridge), liftedDetection("oven", at: far)],
            [liftedDetection("sink", at: -far)],
        ], configuration: configuration)
        XCTAssertEqual(full.tracks.map(\.category), ["refrigerator", "oven"], "confirmed tracks are never evicted")
    }
}
