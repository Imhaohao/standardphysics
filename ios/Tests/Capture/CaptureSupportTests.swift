import ARKit
import CoreVideo
import ImageIO
import RoomPlan
import XCTest
@testable import StandardPhysics

final class CaptureSupportTests: XCTestCase {
    func testCheckpointClockWaitsForGoodMappingThenTwelveSeconds() {
        var clock = CheckpointClock()
        XCTAssertFalse(clock.isDue(at: 0, isMappingGood: false))
        XCTAssertTrue(clock.isDue(at: 1, isMappingGood: true))
        XCTAssertFalse(clock.isDue(at: 12.9, isMappingGood: true))
        XCTAssertFalse(clock.isDue(at: 14, isMappingGood: false))
        XCTAssertTrue(clock.isDue(at: 14, isMappingGood: true))
    }

    func testTrackingStateMapping() {
        XCTAssertEqual(TrackingStatus(ARCamera.TrackingState.normal), .normal)
        XCTAssertEqual(TrackingStatus(ARCamera.TrackingState.notAvailable), .notAvailable)
        XCTAssertEqual(TrackingStatus(ARCamera.TrackingState.limited(.relocalizing)), .limited(.relocalizing))
        XCTAssertEqual(TrackingStatus(ARCamera.TrackingState.limited(.excessiveMotion)), .limited(.excessiveMotion))
    }

    func testMappingStatusWorthSaving() {
        XCTAssertTrue(ARFrame.WorldMappingStatus.mapped.isGoodEnoughToSave)
        XCTAssertTrue(ARFrame.WorldMappingStatus.extending.isGoodEnoughToSave)
        XCTAssertFalse(ARFrame.WorldMappingStatus.limited.isGoodEnoughToSave)
        XCTAssertFalse(ARFrame.WorldMappingStatus.notAvailable.isGoodEnoughToSave)
    }

    func testThermalMapping() {
        XCTAssertEqual(ThermalLevel(ProcessInfo.ThermalState.critical), .critical)
        XCTAssertEqual(ThermalLevel(ProcessInfo.ThermalState.serious), .serious)
        XCTAssertEqual(ThermalLevel(ProcessInfo.ThermalState.nominal), .nominal)
    }

    func testSnapshotIsSmallPortraitJPEG() async throws {
        var buffer: CVPixelBuffer?
        let attributes = [kCVPixelBufferIOSurfacePropertiesKey: [:]] as CFDictionary
        XCTAssertEqual(CVPixelBufferCreate(nil, 1920, 1440, kCVPixelFormatType_32BGRA, attributes, &buffer), kCVReturnSuccess)
        let frame = CVPixelBufferWrapper(buffer: try XCTUnwrap(buffer))
        let encoded = await SnapshotEncoder.jpeg(from: frame)
        let jpeg = try XCTUnwrap(encoded)
        XCTAssertEqual(Array(jpeg.prefix(2)), [0xFF, 0xD8])
        let source = try XCTUnwrap(CGImageSourceCreateWithData(jpeg as CFData, nil))
        let properties = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any])
        XCTAssertEqual(properties[kCGImagePropertyPixelWidth] as? Int, 480)
        XCTAssertEqual(properties[kCGImagePropertyPixelHeight] as? Int, 640)
    }

    func testEveryRoomPlanObjectHasADistinctCategory() {
        let names = CapturedRoom.Object.Category.allCases.map(LiveElementMapper.categoryName)
        XCTAssertEqual(Set(names).count, names.count)
        XCTAssertFalse(names.contains("object"))
        XCTAssertEqual(LiveElementMapper.categoryName(.washerDryer), "washer_dryer")
    }

    func testSurfaceKinds() {
        XCTAssertEqual(LiveElementMapper.describe(.wall).0, .wall)
        XCTAssertEqual(LiveElementMapper.describe(.door(isOpen: true)).1, "door_open")
        XCTAssertEqual(LiveElementMapper.describe(.door(isOpen: false)).0, .door)
        XCTAssertEqual(LiveElementMapper.describe(.window).0, .window)
        XCTAssertEqual(LiveElementMapper.describe(.floor).0, .floor)
        XCTAssertEqual(LiveElementMapper.describe(.opening).0, .opening)
        XCTAssertGreaterThan(LiveElementMapper.confidence(.high), LiveElementMapper.confidence(.medium))
        XCTAssertGreaterThan(LiveElementMapper.confidence(.medium), LiveElementMapper.confidence(.low))
    }

    func testInstructionsBecomePlainLanguage() {
        XCTAssertEqual(ScanInstruction(.moveCloseToWall).text, "Move closer to the wall")
        XCTAssertEqual(ScanInstruction(.slowDown).text, "Slow down")
        XCTAssertNil(ScanInstruction(.normal).text)
        XCTAssertNotNil(ScanInstruction(.lowTexture).text)
        XCTAssertNotNil(ScanInstruction(.turnOnLight).text)
        XCTAssertNotNil(ScanInstruction(.moveAwayFromWall).text)
    }

    func testGuidancePriorities() {
        XCTAssertEqual(GuidanceText.message(for: GuidanceInput(phase: .scanning(room: 0), instruction: .slowDown, isThermalWarning: true)), "Slow down")
        XCTAssertNotNil(GuidanceText.message(for: GuidanceInput(phase: .scanning(room: 0), isThermalWarning: true)))
        XCTAssertNil(GuidanceText.message(for: GuidanceInput(phase: .scanning(room: 0))))
        XCTAssertNil(GuidanceText.message(for: GuidanceInput(phase: .paused(room: 0, reason: .user), instruction: .slowDown)))
        XCTAssertNotNil(GuidanceText.message(for: GuidanceInput(phase: .paused(room: 0, reason: .thermal))))
        let lining = GuidanceText.message(for: GuidanceInput(phase: .relocalizing(room: 1)))
        let timedOut = GuidanceText.message(for: GuidanceInput(phase: .relocalizing(room: 1), relocalizationTimedOut: true))
        XCTAssertNotEqual(lining, timedOut)
        XCTAssertNil(GuidanceText.message(for: GuidanceInput(phase: .betweenRooms(completed: 1))))
    }
}
