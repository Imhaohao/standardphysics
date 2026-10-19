import XCTest
@testable import StandardPhysics

final class RoomSalvageTests: XCTestCase {
    private func room(walls: Int, objects: Int) -> Data {
        let object: [String: Any] = [
            "walls": Array(repeating: ["w": 1], count: walls),
            "objects": Array(repeating: ["o": 1], count: objects),
            "doors": [], "windows": [], "openings": [],
        ]
        return try! JSONSerialization.data(withJSONObject: object)
    }

    private func scanning() -> CaptureState {
        CaptureStateMachine.reduce(CaptureState(), .start).0
    }

    private func run(_ events: [CaptureEvent], from state: CaptureState) -> (CaptureState, [CaptureEffect]) {
        events.reduce((state, [CaptureEffect]())) { partial, event in
            let (next, effects) = CaptureStateMachine.reduce(partial.0, event)
            return (next, partial.1 + effects)
        }
    }

    func testScoreCountsEverySurfaceAndObject() {
        XCTAssertEqual(RoomSalvage.score(room(walls: 4, objects: 12)), 16)
        XCTAssertEqual(RoomSalvage.score(Data("not json".utf8)), 0)
    }

    func testTheFullerCaptureWinsAndTiesGoToTheLatest() {
        let full = room(walls: 4, objects: 12), partial = room(walls: 2, objects: 3)
        XCTAssertEqual(RoomSalvage.better(full, partial), full)
        XCTAssertEqual(RoomSalvage.better(partial, full), full)
        XCTAssertEqual(RoomSalvage.better(nil, partial), partial)
        let sameSize = room(walls: 2, objects: 3)
        XCTAssertEqual(RoomSalvage.better(partial, sameSize), sameSize)
    }

    func testRoomPlanGivingUpAfterControlCenterKeepsWhatWasScanned() {
        let scanned = room(walls: 4, objects: 12)
        let (failed, _) = run([
            .appActivity(.inactive), .appActivity(.active),
            .roomCaptureSalvaged(roomJSON: scanned), .roomCaptureFailed(message: "worldTrackingFailure"),
        ], from: scanning())
        XCTAssertEqual(failed.salvagedRoomJSON, scanned)

        let (_, effects) = run([.userContinue, .roomCaptureEnded(roomJSON: room(walls: 1, objects: 2))], from: failed)
        XCTAssertTrue(effects.contains(.startRoomCapture(room: 0)), "Continue scans the rest of the room")
        XCTAssertTrue(effects.contains(.persistRoom(index: 0, roomJSON: scanned)), "the fuller scan is saved")
    }

    func testFinishingRightAfterRoomPlanGaveUpSavesTheSalvagedRoom() {
        let scanned = room(walls: 4, objects: 12)
        let (failed, _) = run([
            .appActivity(.inactive), .appActivity(.active),
            .roomCaptureSalvaged(roomJSON: scanned), .roomCaptureFailed(message: "worldTrackingFailure"),
        ], from: scanning())
        let (saved, effects) = CaptureStateMachine.reduce(failed, .finishRoom)
        XCTAssertFalse(effects.contains(.finishRoomCapture), "there is no RoomPlan session left to stop")
        XCTAssertTrue(effects.contains(.persistRoom(index: 0, roomJSON: scanned)))
        XCTAssertEqual(saved.phase, .betweenRooms(completed: 1))
        XCTAssertNil(saved.salvagedRoomJSON)
    }

    func testOnEqualCountsTheMoreDetailedCaptureWins() {
        let detailed = try! JSONSerialization.data(withJSONObject: ["walls": [["w": 1, "extra": String(repeating: "x", count: 200)]], "objects": []])
        let sparse = room(walls: 1, objects: 0)
        XCTAssertEqual(RoomSalvage.better(detailed, sparse), detailed)
    }

    func testReachingTheSceneLimitSavesTheRoomInsteadOfStartingOver() {
        let scanned = room(walls: 4, objects: 12)
        let (saved, effects) = run([.roomCaptureSalvaged(roomJSON: scanned), .roomCaptureReachedSceneLimit], from: scanning())
        XCTAssertTrue(effects.contains(.persistRoom(index: 0, roomJSON: scanned)))
        XCTAssertFalse(effects.contains(.startRoomCapture(room: 0)), "no silent restart")
        XCTAssertEqual(saved.phase, .betweenRooms(completed: 1))
        XCTAssertTrue(saved.lastRoomEndedAtSceneLimit)
        XCTAssertEqual(
            GuidanceText.message(for: GuidanceInput(phase: saved.phase, lastRoomEndedAtSceneLimit: saved.lastRoomEndedAtSceneLimit)),
            GuidanceText.sceneLimitMessage
        )
        let next = CaptureStateMachine.reduce(saved, .nextRoom).0
        XCTAssertEqual(next.phase, .scanning(room: 1))
    }

    func testStartingTheRoomAgainDropsTheSalvage() {
        let (failed, _) = run([.roomCaptureSalvaged(roomJSON: room(walls: 4, objects: 1)), .roomCaptureFailed(message: "x")], from: scanning())
        XCTAssertNil(CaptureStateMachine.reduce(failed, .restartRoom).0.salvagedRoomJSON)
    }

    func testGuidanceSaysTheScanWasKept() {
        let kept = GuidanceText.message(for: GuidanceInput(phase: .scanning(room: 0), lastRoomCaptureError: "x", hasSalvagedRoom: true))
        XCTAssertEqual(kept, "We kept what you scanned. Keep going to fill in the rest.")
        let lost = GuidanceText.message(for: GuidanceInput(phase: .scanning(room: 0), lastRoomCaptureError: "x"))
        XCTAssertEqual(lost, "That room didn't save, so scan it once more")
    }
}
