import XCTest
@testable import StandardPhysics

final class CaptureStateMachineTests: XCTestCase {
    private let roomJSON = Data("{\"room\":1}".utf8)

    private func run(_ events: [CaptureEvent], from state: CaptureState = CaptureState()) -> (CaptureState, [CaptureEffect]) {
        events.reduce((state, [CaptureEffect]())) { partial, event in
            let (next, effects) = CaptureStateMachine.reduce(partial.0, event)
            return (next, partial.1 + effects)
        }
    }

    private func reduce(_ state: CaptureState, _ event: CaptureEvent) -> (CaptureState, [CaptureEffect]) {
        CaptureStateMachine.reduce(state, event)
    }

    private func scanning() -> CaptureState {
        run([.start, .tracking(.normal)]).0
    }

    // MARK: Start

    func testStartRunsFreshSessionAndCapturesFirstRoom() {
        let (state, effects) = reduce(CaptureState(), .start)
        XCTAssertEqual(state.phase, .scanning(room: 0))
        XCTAssertEqual(effects, [
            .runARSession(.fresh),
            .startRoomCapture(room: 0),
            .setIdleTimerDisabled(true),
            .persistManifest,
        ])
    }

    func testStartIsIgnoredWhileScanning() {
        let (state, effects) = reduce(scanning(), .start)
        XCTAssertEqual(state, scanning())
        XCTAssertEqual(effects, [])
    }

    // MARK: Scene phase never finishes

    func testInactivePausesWithoutStoppingAnything() {
        let (state, effects) = reduce(scanning(), .appActivity(.inactive))
        XCTAssertEqual(state.phase, .paused(room: 0, reason: .appInactive))
        XCTAssertEqual(effects, [.persistManifest])
    }

    func testBackgroundPausesARSessionAndActiveResumesIt() {
        let (background, pauseEffects) = run([.appActivity(.inactive), .appActivity(.background)], from: scanning())
        XCTAssertEqual(background.phase, .paused(room: 0, reason: .backgrounded))
        XCTAssertEqual(reduce(scanning(), .appActivity(.background)).1, [.pauseARSession, .persistManifest])
        XCTAssertFalse(pauseEffects.contains(.finishRoomCapture))

        let (active, resumeEffects) = run([.appActivity(.inactive), .appActivity(.active)], from: background)
        XCTAssertEqual(active.phase, .scanning(room: 0))
        XCTAssertTrue(resumeEffects.contains(.runARSession(.continueExisting)))
        XCTAssertFalse(resumeEffects.contains(.startRoomCapture(room: 0)))
    }

    func testNoScenePhaseSequenceEverFinishesTheScan() {
        let phases: [AppActivity] = [.inactive, .background, .inactive, .active, .background, .active, .inactive]
        var state = scanning()
        for phase in phases {
            let (next, effects) = reduce(state, .appActivity(phase))
            XCTAssertFalse(effects.contains(.finishRoomCapture))
            XCTAssertFalse(effects.contains(.exportStructure))
            XCTAssertFalse(effects.contains(.cancelRoomCapture))
            state = next
        }
        XCTAssertEqual(state.phase, .paused(room: 0, reason: .appInactive))
    }

    func testWillResignActiveCheckpoints() {
        XCTAssertEqual(reduce(scanning(), .appWillResignActive).1, [.saveCheckpoint])
    }

    // MARK: Session interruption

    func testInterruptionPausesAndRelocalizesOnResume() {
        let (interrupted, effects) = reduce(scanning(), .sessionInterrupted)
        XCTAssertEqual(interrupted.phase, .paused(room: 0, reason: .sessionInterrupted))
        XCTAssertEqual(effects, [.persistManifest])

        let (ended, _) = reduce(interrupted, .sessionInterruptionEnded)
        XCTAssertEqual(ended.phase, .scanning(room: 0))

        let (relocalizing, relocEffects) = reduce(ended, .tracking(.limited(.relocalizing)))
        XCTAssertEqual(relocalizing.phase, .relocalizing(room: 0))
        XCTAssertEqual(relocEffects, [.startRelocalizationTimer, .persistManifest])

        let (resumed, resumeEffects) = reduce(relocalizing, .tracking(.normal))
        XCTAssertEqual(resumed.phase, .scanning(room: 0))
        XCTAssertEqual(resumeEffects, [.cancelRelocalizationTimer, .persistManifest])
    }

    func testInterruptionWhileBackgroundedReportsBackgroundFirst() {
        let (state, _) = run([.appActivity(.background), .sessionInterrupted], from: scanning())
        XCTAssertEqual(state.phase, .paused(room: 0, reason: .backgrounded))
        let (foreground, _) = reduce(state, .appActivity(.active))
        XCTAssertEqual(foreground.phase, .paused(room: 0, reason: .sessionInterrupted))
    }

    func testRoomCaptureFailureDuringInterruptionRestartsWhenResumed() {
        let (failed, effects) = run([.sessionInterrupted, .roomCaptureFailed(message: "worldTrackingFailure")], from: scanning())
        XCTAssertFalse(effects.contains(.startRoomCapture(room: 0)))
        XCTAssertEqual(failed.lastRoomCaptureError, "worldTrackingFailure")
        let (resumed, resumeEffects) = reduce(failed, .sessionInterruptionEnded)
        XCTAssertEqual(resumed.phase, .scanning(room: 0))
        XCTAssertEqual(resumeEffects, [.startRoomCapture(room: 0), .persistManifest])
    }

    func testRoomCaptureFailureDuringRelocalizationStartsCaptureAfterwards() {
        let (state, _) = run([
            .tracking(.limited(.relocalizing)),
            .roomCaptureFailed(message: "lost"),
            .tracking(.normal),
        ], from: scanning())
        XCTAssertEqual(state.phase, .scanning(room: 0))
        let (_, effects) = run([.tracking(.limited(.relocalizing)), .roomCaptureFailed(message: "lost")], from: scanning())
        XCTAssertFalse(effects.contains(.startRoomCapture(room: 0)))
        let (_, finalEffects) = reduce(run([.tracking(.limited(.relocalizing)), .roomCaptureFailed(message: "lost")], from: scanning()).0, .tracking(.normal))
        XCTAssertEqual(finalEffects, [.cancelRelocalizationTimer, .startRoomCapture(room: 0), .persistManifest])
    }

    // MARK: Tracking

    func testTrackingNotAvailablePausesAndNormalResumes() {
        let (lost, _) = reduce(scanning(), .tracking(.notAvailable))
        XCTAssertEqual(lost.phase, .paused(room: 0, reason: .trackingLost))
        XCTAssertEqual(reduce(lost, .tracking(.normal)).0.phase, .scanning(room: 0))
    }

    func testLimitedTrackingOtherThanRelocalizingKeepsScanning() {
        for reason: LimitedTrackingReason in [.initializing, .excessiveMotion, .insufficientFeatures] {
            let (state, effects) = reduce(scanning(), .tracking(.limited(reason)))
            XCTAssertEqual(state.phase, .scanning(room: 0))
            XCTAssertEqual(effects, [])
        }
    }

    func testNoCheckpointWhileTrackingLostOrRelocalizing() {
        XCTAssertEqual(run([.tracking(.notAvailable), .checkpointDue], from: scanning()).1.filter { $0 == .saveCheckpoint }, [])
        XCTAssertEqual(reduce(run([.tracking(.limited(.relocalizing))], from: scanning()).0, .checkpointDue).1, [])
    }

    func testCheckpointDueWhileScanning() {
        XCTAssertEqual(reduce(scanning(), .checkpointDue).1, [.saveCheckpoint])
        XCTAssertEqual(reduce(CaptureState(), .checkpointDue).1, [])
    }

    // MARK: Thermal

    func testCriticalThermalCheckpointsThenPausesSession() {
        let (hot, effects) = reduce(scanning(), .thermal(.critical))
        XCTAssertEqual(hot.phase, .paused(room: 0, reason: .thermal))
        XCTAssertEqual(effects, [.saveCheckpoint, .pauseARSession, .persistManifest])
        let (cooled, coolEffects) = reduce(hot, .thermal(.fair))
        XCTAssertEqual(cooled.phase, .scanning(room: 0))
        XCTAssertEqual(coolEffects, [.runARSession(.continueExisting), .persistManifest])
    }

    func testSeriousThermalOnlyWarns() {
        let (warm, effects) = reduce(scanning(), .thermal(.serious))
        XCTAssertTrue(warm.isThermalWarning)
        XCTAssertEqual(warm.phase, .scanning(room: 0))
        XCTAssertEqual(effects, [])
    }

    // MARK: User pause

    func testUserPauseAndContinue() {
        let (paused, effects) = reduce(scanning(), .userPause)
        XCTAssertEqual(paused.phase, .paused(room: 0, reason: .user))
        XCTAssertEqual(effects, [.saveCheckpoint, .pauseARSession, .persistManifest])
        let (resumed, resumeEffects) = reduce(paused, .userContinue)
        XCTAssertEqual(resumed.phase, .scanning(room: 0))
        XCTAssertEqual(resumeEffects, [.runARSession(.continueExisting), .persistManifest])
    }

    func testUserPauseSurvivesBackgroundRoundTrip() {
        let (state, _) = run([.userPause, .appActivity(.background), .appActivity(.active)], from: scanning())
        XCTAssertEqual(state.phase, .paused(room: 0, reason: .user))
        XCTAssertFalse(state.isARSessionRunning)
    }

    // MARK: Rooms

    func testFinishRoomSavesRoomCheckpointsAndExportsMesh() {
        let (saving, effects) = reduce(scanning(), .finishRoom)
        XCTAssertEqual(effects, [.finishRoomCapture, .persistManifest])
        XCTAssertEqual(saving.phase, .betweenRooms(completed: 0))

        let (between, endEffects) = reduce(saving, .roomCaptureEnded(roomJSON: roomJSON))
        XCTAssertEqual(between.phase, .betweenRooms(completed: 1))
        XCTAssertEqual(endEffects, [.persistRoom(index: 0, roomJSON: roomJSON), .saveCheckpoint, .exportMesh, .persistManifest])
    }

    func testNextRoomKeepsTheSameSession() {
        let (state, effects) = run([.finishRoom, .roomCaptureEnded(roomJSON: roomJSON), .nextRoom], from: scanning())
        XCTAssertEqual(state.phase, .scanning(room: 1))
        XCTAssertFalse(effects.contains { if case .runARSession = $0 { true } else { false } })
        XCTAssertEqual(effects.last, .persistManifest)
        XCTAssertTrue(effects.contains(.startRoomCapture(room: 1)))
    }

    func testRoomBuildFailureRestartsSameRoom() {
        let (state, effects) = run([.finishRoom, .roomCaptureFailed(message: "insufficientInput")], from: scanning())
        XCTAssertEqual(state.phase, .scanning(room: 0))
        XCTAssertEqual(state.lastRoomCaptureError, "insufficientInput")
        XCTAssertEqual(effects.suffix(2), [.startRoomCapture(room: 0), .persistManifest])
    }

    func testCapsRoomsPerStructureAtEight() {
        var state = scanning()
        for _ in 0..<CaptureState.maxRoomsPerStructure {
            state = run([.finishRoom, .roomCaptureEnded(roomJSON: roomJSON)], from: state).0
            state = reduce(state, .nextRoom).0
        }
        XCTAssertEqual(state.completedRooms, 8)
        XCTAssertEqual(state.phase, .betweenRooms(completed: 8))
        XCTAssertFalse(state.canStartNextRoom)
        XCTAssertEqual(reduce(state, .nextRoom).1, [])
    }

    func testFinishRoomIgnoredUnlessCapturing() {
        XCTAssertEqual(reduce(CaptureState(), .finishRoom).1, [])
        let between = run([.finishRoom, .roomCaptureEnded(roomJSON: roomJSON)], from: scanning()).0
        XCTAssertEqual(reduce(between, .finishRoom).1, [])
    }

    // MARK: Finishing

    func testFinishScanWhileCapturingSavesRoomThenExports() {
        let (saving, effects) = reduce(scanning(), .finishScan)
        XCTAssertEqual(saving.phase, .finishing)
        XCTAssertEqual(effects, [.finishRoomCapture, .persistManifest])
        let (finishing, endEffects) = reduce(saving, .roomCaptureEnded(roomJSON: roomJSON))
        XCTAssertEqual(finishing.activity, .finishing)
        XCTAssertEqual(endEffects, [.persistRoom(index: 0, roomJSON: roomJSON), .saveCheckpoint, .exportMesh, .exportStructure])
        let (finished, finishEffects) = reduce(finishing, .exportFinished)
        XCTAssertEqual(finished.phase, .finished)
        XCTAssertEqual(finishEffects, [.pauseARSession, .setIdleTimerDisabled(false), .persistManifest])
    }

    func testFinishScanBetweenRoomsExportsImmediately() {
        let between = run([.finishRoom, .roomCaptureEnded(roomJSON: roomJSON)], from: scanning()).0
        let (state, effects) = reduce(between, .finishScan)
        XCTAssertEqual(state.phase, .finishing)
        XCTAssertEqual(effects, [.exportStructure, .persistManifest])
    }

    func testFinishScanAfterFinishRoomWaitsForRoom() {
        let (state, effects) = run([.finishRoom, .finishScan], from: scanning())
        XCTAssertEqual(state.activity, .savingRoom(finishScanAfterwards: true))
        XCTAssertEqual(effects.filter { $0 == .finishRoomCapture }.count, 1)
    }

    func testFinishScanWithFailedLastRoomStillExportsEarlierRooms() {
        let between = run([.finishRoom, .roomCaptureEnded(roomJSON: roomJSON), .nextRoom], from: scanning()).0
        let (state, _) = run([.finishScan, .roomCaptureFailed(message: "x")], from: between)
        XCTAssertEqual(state.activity, .finishing)
    }

    func testFinishScanWithNothingCapturedIsIgnored() {
        XCTAssertEqual(reduce(CaptureState(), .finishScan).1, [])
    }

    func testExportFailureFails() {
        let finishing = run([.finishScan, .roomCaptureEnded(roomJSON: roomJSON)], from: scanning()).0
        let (failed, effects) = reduce(finishing, .exportFailed(message: "disk full"))
        XCTAssertEqual(failed.phase, .failed(message: "disk full"))
        XCTAssertEqual(effects, [.pauseARSession, .setIdleTimerDisabled(false), .persistManifest])
    }

    func testSessionFailureCancelsCaptureAndFails() {
        let (state, effects) = reduce(scanning(), .sessionFailed(message: "camera denied"))
        XCTAssertEqual(state.phase, .failed(message: "camera denied"))
        XCTAssertEqual(effects, [.cancelRoomCapture, .pauseARSession, .setIdleTimerDisabled(false), .persistManifest])
    }

    // MARK: Discard

    func testDiscardCancelsDeletesAndReturnsToIdle() {
        let (state, effects) = reduce(scanning(), .discard)
        XCTAssertEqual(state.phase, .idle)
        XCTAssertEqual(effects, [.cancelRoomCapture, .deleteScan, .pauseARSession, .setIdleTimerDisabled(false)])
    }

    func testDiscardWhileRelocalizingCancelsTimer() {
        let relocalizing = reduce(CaptureState(), .resume(ResumePoint(completedRooms: 1, hasWorldMap: true, wasBetweenRooms: false))).0
        let effects = reduce(relocalizing, .discard).1
        XCTAssertEqual(effects, [.cancelRelocalizationTimer, .deleteScan, .pauseARSession, .setIdleTimerDisabled(false)])
    }

    // MARK: Kill, relaunch, relocalize, continue

    func testKillDuringRoomThenRelaunchRelocalizesAndContinuesSameRoom() {
        let beforeKill = run([.finishRoom, .roomCaptureEnded(roomJSON: roomJSON), .nextRoom, .checkpointDue], from: scanning()).0
        XCTAssertEqual(beforeKill.phase, .scanning(room: 1))

        let point = ResumePoint(completedRooms: beforeKill.completedRooms, hasWorldMap: true, wasBetweenRooms: false)
        let (relocalizing, effects) = reduce(CaptureState(), .resume(point))
        XCTAssertEqual(relocalizing.phase, .relocalizing(room: 1))
        XCTAssertEqual(effects, [
            .runARSession(.relocalize),
            .startRelocalizationTimer,
            .setIdleTimerDisabled(true),
            .persistManifest,
        ])

        let (stillRelocalizing, limitedEffects) = reduce(relocalizing, .tracking(.limited(.relocalizing)))
        XCTAssertEqual(stillRelocalizing.phase, .relocalizing(room: 1))
        XCTAssertEqual(limitedEffects, [])
        XCTAssertEqual(reduce(stillRelocalizing, .checkpointDue).1, [], "must not overwrite the saved map before relocalizing")

        let (continued, continueEffects) = reduce(stillRelocalizing, .tracking(.normal))
        XCTAssertEqual(continued.phase, .scanning(room: 1))
        XCTAssertEqual(continueEffects, [.cancelRelocalizationTimer, .startRoomCapture(room: 1), .persistManifest])
        XCTAssertEqual(reduce(continued, .checkpointDue).1, [.saveCheckpoint])
    }

    func testRelocalizedEventBehavesLikeNormalTracking() {
        let relocalizing = reduce(CaptureState(), .resume(ResumePoint(completedRooms: 2, hasWorldMap: true, wasBetweenRooms: false))).0
        XCTAssertEqual(reduce(relocalizing, .relocalized).0.phase, .scanning(room: 2))
    }

    func testRelocalizationTimeoutOffersRestartWhichStartsFreshFrame() {
        let relocalizing = reduce(CaptureState(), .resume(ResumePoint(completedRooms: 1, hasWorldMap: true, wasBetweenRooms: false))).0
        let (timedOut, timeoutEffects) = reduce(relocalizing, .relocalizationTimedOut)
        XCTAssertTrue(timedOut.relocalizationTimedOut)
        XCTAssertEqual(timedOut.phase, .relocalizing(room: 1))
        XCTAssertEqual(timeoutEffects, [])

        let (restarted, effects) = reduce(timedOut, .restartRoom)
        XCTAssertEqual(restarted.phase, .scanning(room: 1))
        XCTAssertFalse(restarted.relocalizationTimedOut)
        XCTAssertEqual(effects, [.cancelRelocalizationTimer, .runARSession(.fresh), .startRoomCapture(room: 1), .persistManifest])
    }

    func testInProcessRelocalizationRestartCancelsRunningRoomCapture() {
        let relocalizing = reduce(scanning(), .tracking(.limited(.relocalizing))).0
        let effects = run([.relocalizationTimedOut, .restartRoom], from: relocalizing).1
        XCTAssertEqual(effects, [.cancelRelocalizationTimer, .cancelRoomCapture, .runARSession(.fresh), .startRoomCapture(room: 0), .persistManifest])
    }

    func testRestartRoomWhileCapturingRescansInSameSession() {
        let (state, effects) = reduce(scanning(), .restartRoom)
        XCTAssertEqual(state.phase, .scanning(room: 0))
        XCTAssertEqual(effects, [.cancelRoomCapture, .startRoomCapture(room: 0)])
        XCTAssertEqual(reduce(run([.finishRoom, .roomCaptureEnded(roomJSON: roomJSON)], from: scanning()).0, .restartRoom).1, [])
    }

    func testRelaunchBetweenRoomsDefersRelocalizationToNextRoom() {
        let (between, effects) = reduce(CaptureState(), .resume(ResumePoint(completedRooms: 2, hasWorldMap: true, wasBetweenRooms: true)))
        XCTAssertEqual(between.phase, .betweenRooms(completed: 2))
        XCTAssertEqual(effects, [.setIdleTimerDisabled(true), .persistManifest])

        let (relocalizing, nextEffects) = reduce(between, .nextRoom)
        XCTAssertEqual(relocalizing.phase, .relocalizing(room: 2))
        XCTAssertEqual(nextEffects, [.runARSession(.relocalize), .startRelocalizationTimer, .persistManifest])
        XCTAssertEqual(reduce(relocalizing, .tracking(.normal)).1, [.cancelRelocalizationTimer, .startRoomCapture(room: 2), .persistManifest])
    }

    func testRelaunchBetweenRoomsCanFinishWithoutRelocalizing() {
        let between = reduce(CaptureState(), .resume(ResumePoint(completedRooms: 2, hasWorldMap: true, wasBetweenRooms: true))).0
        let (state, effects) = reduce(between, .finishScan)
        XCTAssertEqual(state.phase, .finishing)
        XCTAssertEqual(effects, [.exportStructure, .persistManifest])
    }

    func testRelaunchWithoutWorldMapStartsFreshCapture() {
        let (state, effects) = reduce(CaptureState(), .resume(ResumePoint(completedRooms: 1, hasWorldMap: false, wasBetweenRooms: false)))
        XCTAssertEqual(state.phase, .scanning(room: 1))
        XCTAssertEqual(effects, [.runARSession(.fresh), .startRoomCapture(room: 1), .setIdleTimerDisabled(true), .persistManifest])
    }

    func testRelaunchWithFullStructureLandsBetweenRooms() {
        let state = reduce(CaptureState(), .resume(ResumePoint(completedRooms: 8, hasWorldMap: true, wasBetweenRooms: false))).0
        XCTAssertEqual(state.phase, .betweenRooms(completed: 8))
        XCTAssertFalse(state.canStartNextRoom)
    }

    func testInterruptDuringRelocalizationAfterRelaunchPausesThenContinues() {
        let relocalizing = reduce(CaptureState(), .resume(ResumePoint(completedRooms: 1, hasWorldMap: true, wasBetweenRooms: false))).0
        let (backgrounded, effects) = reduce(relocalizing, .appActivity(.background))
        XCTAssertEqual(backgrounded.phase, .paused(room: 1, reason: .backgrounded))
        XCTAssertEqual(effects, [.pauseARSession, .persistManifest])
        let (back, backEffects) = reduce(backgrounded, .appActivity(.active))
        XCTAssertEqual(back.phase, .relocalizing(room: 1))
        XCTAssertEqual(backEffects, [.runARSession(.continueExisting), .persistManifest])
        XCTAssertEqual(reduce(back, .tracking(.normal)).0.phase, .scanning(room: 1))
    }

    func testResumeIgnoredWhenAlreadyScanning() {
        XCTAssertEqual(reduce(scanning(), .resume(ResumePoint(completedRooms: 3, hasWorldMap: true, wasBetweenRooms: false))).1, [])
    }
}
