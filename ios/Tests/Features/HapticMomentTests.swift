import XCTest
@testable import StandardPhysics

@MainActor
final class HapticMomentTests: XCTestCase {
    func testRouteMoments() {
        XCTAssertEqual(HapticMoment.forRoute(from: .capture, to: .processing), .scanFinished)
        XCTAssertEqual(HapticMoment.forRoute(from: .processing, to: .results(UUID())), .reportReady)
        XCTAssertNil(HapticMoment.forRoute(from: .home, to: .results(UUID())), "opening an old report is not news")
        XCTAssertNil(HapticMoment.forRoute(from: .home, to: .beforeYouScan))
    }

    func testOnlyAJustFinishedRoomBuzzes() {
        XCTAssertEqual(HapticMoment.forPhase(from: .scanning(room: 1), to: .betweenRooms(completed: 1)), .roomFinished)
        XCTAssertEqual(HapticMoment.forPhase(from: .paused(room: 2, reason: .user), to: .betweenRooms(completed: 2)), .roomFinished)
        XCTAssertNil(HapticMoment.forPhase(from: .idle, to: .betweenRooms(completed: 2)), "resuming between rooms")
        XCTAssertNil(HapticMoment.forPhase(from: .scanning(room: 1), to: .paused(room: 1, reason: .user)))
    }
}
