import XCTest
@testable import StandardPhysics

final class SceneCaptureConfigurationTests: XCTestCase {
    func testPrefersClassifiedMeshAndDepthPersonSegmentation() {
        let options = SceneCaptureOptions.select(from: SceneCaptureCapabilities(
            supportsMesh: true,
            supportsMeshWithClassification: true,
            supportsPersonSegmentationWithDepth: true,
            supportsPersonSegmentation: true
        ))

        XCTAssertEqual(options.reconstruction, .meshWithClassification)
        XCTAssertTrue(options.usesPersonSegmentationWithDepth)
        XCTAssertFalse(options.usesPersonSegmentation)
        XCTAssertTrue(options.peopleFilteringEnabled)
    }

    func testFallsBackToBasicPersonSegmentationWithoutDepth() {
        let options = SceneCaptureOptions.select(from: SceneCaptureCapabilities(
            supportsMesh: true,
            supportsMeshWithClassification: false,
            supportsPersonSegmentationWithDepth: false,
            supportsPersonSegmentation: true
        ))

        XCTAssertEqual(options.reconstruction, .mesh)
        XCTAssertFalse(options.usesPersonSegmentationWithDepth)
        XCTAssertTrue(options.usesPersonSegmentation)
        XCTAssertTrue(options.peopleFilteringEnabled)
    }

    func testUnsupportedCapabilitiesDoNotSetUnsupportedFlags() {
        let options = SceneCaptureOptions.select(from: SceneCaptureCapabilities(
            supportsMesh: false,
            supportsMeshWithClassification: false,
            supportsPersonSegmentationWithDepth: false,
            supportsPersonSegmentation: false
        ))

        XCTAssertNil(options.reconstruction)
        XCTAssertFalse(options.peopleFilteringEnabled)
        XCTAssertFalse(options.usesPersonSegmentationWithDepth)
        XCTAssertFalse(options.usesPersonSegmentation)
    }
}
