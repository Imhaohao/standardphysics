import Foundation

/// Pure reducer for the capture flow. Interruptions of any kind pause; only an explicit
/// `finishScan` ever ends a walk.
nonisolated enum CaptureStateMachine {
    static func reduce(_ state: CaptureState, _ event: CaptureEvent) -> (CaptureState, [CaptureEffect]) {
        var transition = Transition(state: state)
        transition.apply(event)
        transition.reconcile(from: state)
        return (transition.state, transition.effects)
    }
}

private nonisolated struct Transition {
    var state: CaptureState
    var effects: [CaptureEffect] = []

    mutating func apply(_ event: CaptureEvent) {
        switch event {
        case .start: start()
        case .resume(let point): resume(point)
        case .appActivity(let activity): appActivity(activity)
        case .appWillResignActive: checkpointIfPossible()
        case .sessionInterrupted:
            state.isSessionInterrupted = true
            holdPause(.sessionInterrupted)
        case .sessionInterruptionEnded: state.isSessionInterrupted = false
        case .sessionFailed(let message): fail(message)
        case .tracking(let status): track(status)
        case .thermal(let level): thermal(level)
        case .checkpointDue: checkpointIfPossible()
        case .roomCaptureEnded(let json): roomEnded(json)
        case .roomCaptureFailed(let message): roomFailed(message)
        case .roomCaptureSalvaged(let json): salvaged(json)
        case .userPause: userPause()
        case .userContinue: userContinue()
        case .finishRoom: finishRoom()
        case .nextRoom: nextRoom()
        case .relocalized: relocalized()
        case .relocalizationTimedOut: relocalizationTimedOut()
        case .restartRoom: restartRoom()
        case .finishScan: finishScan()
        case .exportFinished: exportFinished()
        case .exportFailed(let message): exportFailed(message)
        case .discard: discard()
        }
    }

    // MARK: Starting and resuming

    private mutating func start() {
        guard state.activity == .idle else { return }
        state.completedRooms = 0
        beginCapture(runMode: .fresh)
    }

    private mutating func resume(_ point: ResumePoint) {
        guard state.activity == .idle else { return }
        state.completedRooms = min(point.completedRooms, CaptureState.maxRoomsPerStructure)
        state.needsRelocalization = point.hasWorldMap
        if point.wasBetweenRooms || state.completedRooms >= CaptureState.maxRoomsPerStructure {
            state.activity = .betweenRooms
            return
        }
        if point.hasWorldMap {
            beginRelocalization()
        } else {
            beginCapture(runMode: .fresh)
        }
    }

    private mutating func beginCapture(runMode: ARRunMode) {
        state.activity = .capturing
        state.needsRelocalization = false
        state.relocalizationTimedOut = false
        runSession(runMode)
        effects.append(.startRoomCapture(room: state.currentRoom))
    }

    private mutating func beginRelocalization() {
        state.activity = .relocalizing(roomCaptureRunning: false)
        state.relocalizationTimedOut = false
        runSession(.relocalize)
        effects.append(.startRelocalizationTimer)
    }

    private mutating func runSession(_ mode: ARRunMode) {
        state.isARSessionRunning = true
        effects.append(.runARSession(mode))
    }

    // MARK: Tracking and relocalization

    private mutating func track(_ status: TrackingStatus) {
        state.isTrackingUnavailable = status == .notAvailable
        if status == .limited(.relocalizing), state.activity == .capturing {
            state.activity = .relocalizing(roomCaptureRunning: true)
            state.relocalizationTimedOut = false
            effects.append(.startRelocalizationTimer)
        }
        if status == .normal {
            relocalized()
        }
    }

    private mutating func relocalized() {
        guard case .relocalizing(let roomCaptureRunning) = state.activity else { return }
        state.activity = .capturing
        state.needsRelocalization = false
        state.relocalizationTimedOut = false
        effects.append(.cancelRelocalizationTimer)
        if !roomCaptureRunning {
            effects.append(.startRoomCapture(room: state.currentRoom))
        }
    }

    private mutating func relocalizationTimedOut() {
        guard case .relocalizing = state.activity else { return }
        state.relocalizationTimedOut = true
    }

    /// Drops the room in progress. While relocalizing this also gives up on the saved frame.
    private mutating func restartRoom() {
        state.heldPauseReason = nil
        state.salvagedRoomJSON = nil
        switch state.activity {
        case .capturing:
            state.roomCaptureNeedsRestart = false
            effects.append(contentsOf: [.cancelRoomCapture, .startRoomCapture(room: state.currentRoom)])
        case .relocalizing(let roomCaptureRunning):
            effects.append(.cancelRelocalizationTimer)
            if roomCaptureRunning { effects.append(.cancelRoomCapture) }
            beginCapture(runMode: .fresh)
        default:
            return
        }
    }

    // MARK: Interruptions

    private mutating func thermal(_ level: ThermalLevel) {
        state.isThermalWarning = level == .serious
        let becomesCritical = level == .critical && !state.isThermalCritical
        if becomesCritical {
            checkpointIfPossible()
        }
        state.isThermalCritical = level == .critical
    }

    private mutating func appActivity(_ activity: AppActivity) {
        state.app = activity
        switch activity {
        case .active: return
        case .inactive: holdPause(.appInactive)
        case .background: holdPause(.backgrounded)
        }
    }

    /// Keeps the first reason: Control Center then the app switcher still reads as "you left the app".
    private mutating func holdPause(_ reason: PauseReason) {
        guard state.isScanningRoom, !state.isUserPaused, state.heldPauseReason == nil else { return }
        state.heldPauseReason = reason
    }

    private mutating func userContinue() {
        state.isUserPaused = false
        state.heldPauseReason = nil
    }

    private mutating func userPause() {
        guard state.isScanInProgress, state.activity != .finishing else { return }
        checkpointIfPossible()
        state.isUserPaused = true
    }

    private mutating func checkpointIfPossible() {
        guard state.canCheckpoint else { return }
        effects.append(.saveCheckpoint)
    }

    // MARK: Rooms

    private mutating func finishRoom() {
        guard state.activity == .capturing else { return }
        state.activity = .savingRoom(finishScanAfterwards: false)
        endRoomCapture()
    }

    /// When RoomPlan already gave up there is no session to stop, so the salvaged room is the room.
    private mutating func endRoomCapture() {
        guard state.roomCaptureNeedsRestart, let salvaged = state.salvagedRoomJSON else {
            effects.append(.finishRoomCapture)
            return
        }
        state.roomCaptureNeedsRestart = false
        roomEnded(salvaged)
    }

    private mutating func salvaged(_ json: Data) {
        guard state.isRoomCaptureRunning else { return }
        state.salvagedRoomJSON = RoomSalvage.better(state.salvagedRoomJSON, json)
    }

    private mutating func nextRoom() {
        guard state.canStartNextRoom else { return }
        if state.needsRelocalization {
            beginRelocalization()
        } else {
            state.activity = .capturing
            effects.append(.startRoomCapture(room: state.currentRoom))
        }
    }

    private mutating func roomEnded(_ json: Data) {
        let finishScanAfterwards: Bool
        switch state.activity {
        case .savingRoom(let finish): finishScanAfterwards = finish
        case .capturing: finishScanAfterwards = false
        default: return
        }
        effects.append(.persistRoom(index: state.currentRoom, roomJSON: RoomSalvage.better(state.salvagedRoomJSON, json)))
        state.salvagedRoomJSON = nil
        state.completedRooms += 1
        state.lastRoomCaptureError = nil
        checkpointIfPossible()
        effects.append(.exportMesh)
        if finishScanAfterwards {
            beginFinishing()
        } else {
            state.activity = .betweenRooms
        }
    }

    private mutating func roomFailed(_ message: String) {
        state.lastRoomCaptureError = message
        switch state.activity {
        case .savingRoom(let finishScanAfterwards):
            savingRoomFailed(finishScanAfterwards: finishScanAfterwards)
        case .capturing:
            state.roomCaptureNeedsRestart = true
        case .relocalizing(roomCaptureRunning: true):
            state.activity = .relocalizing(roomCaptureRunning: false)
        default:
            return
        }
    }

    private mutating func savingRoomFailed(finishScanAfterwards: Bool) {
        if finishScanAfterwards, state.completedRooms > 0 {
            beginFinishing()
            return
        }
        state.activity = .capturing
        effects.append(.startRoomCapture(room: state.currentRoom))
    }

    // MARK: Finishing

    private mutating func finishScan() {
        switch state.activity {
        case .capturing:
            state.activity = .savingRoom(finishScanAfterwards: true)
            endRoomCapture()
        case .savingRoom:
            state.activity = .savingRoom(finishScanAfterwards: true)
        case .betweenRooms where state.completedRooms > 0:
            beginFinishing()
        case .relocalizing(let roomCaptureRunning) where state.completedRooms > 0:
            effects.append(.cancelRelocalizationTimer)
            if roomCaptureRunning { effects.append(.cancelRoomCapture) }
            beginFinishing()
        default:
            return
        }
    }

    private mutating func beginFinishing() {
        state.activity = .finishing
        state.isUserPaused = false
        state.heldPauseReason = nil
        effects.append(.exportStructure)
    }

    private mutating func exportFinished() {
        guard state.activity == .finishing else { return }
        state.activity = .finished
    }

    private mutating func exportFailed(_ message: String) {
        guard state.activity == .finishing else { return }
        state.activity = .failed(message)
    }

    private mutating func fail(_ message: String) {
        guard state.isScanInProgress else { return }
        if state.isRoomCaptureRunning { effects.append(.cancelRoomCapture) }
        if case .relocalizing = state.activity { effects.append(.cancelRelocalizationTimer) }
        state.activity = .failed(message)
    }

    private mutating func discard() {
        guard state.activity != .idle else { return }
        if state.isRoomCaptureRunning { effects.append(.cancelRoomCapture) }
        if case .relocalizing = state.activity { effects.append(.cancelRelocalizationTimer) }
        effects.append(.deleteScan)
        var reset = CaptureState()
        reset.app = state.app
        reset.isARSessionRunning = state.isARSessionRunning
        reset.isIdleTimerDisabled = state.isIdleTimerDisabled
        state = reset
    }

    // MARK: Derived effects

    mutating func reconcile(from previous: CaptureState) {
        restartRoomCaptureIfReady()
        reconcileARSession()
        reconcileIdleTimer()
        if state.phase != previous.phase, state.activity != .idle {
            effects.append(.persistManifest)
        }
    }

    private mutating func restartRoomCaptureIfReady() {
        guard state.roomCaptureNeedsRestart, state.activity == .capturing, state.pauseReason == nil else { return }
        state.roomCaptureNeedsRestart = false
        effects.append(.startRoomCapture(room: state.currentRoom))
    }

    private mutating func reconcileARSession() {
        let wanted = state.wantsARSessionRunning
        guard wanted != state.isARSessionRunning else { return }
        state.isARSessionRunning = wanted
        effects.append(wanted ? .runARSession(.continueExisting) : .pauseARSession)
    }

    private mutating func reconcileIdleTimer() {
        let wanted = state.isScanInProgress
        guard wanted != state.isIdleTimerDisabled else { return }
        state.isIdleTimerDisabled = wanted
        effects.append(.setIdleTimerDisabled(wanted))
    }
}
