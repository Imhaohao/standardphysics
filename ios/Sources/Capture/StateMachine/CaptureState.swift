import Foundation

nonisolated struct CaptureState: Sendable, Equatable {
    static let maxRoomsPerStructure = 8

    nonisolated enum Activity: Sendable, Equatable {
        case idle
        case capturing
        case relocalizing(roomCaptureRunning: Bool)
        case savingRoom(finishScanAfterwards: Bool)
        case betweenRooms
        case finishing
        case finished
        case failed(String)
    }

    var activity: Activity = .idle
    var completedRooms = 0
    var app: AppActivity = .active
    var isSessionInterrupted = false
    var isUserPaused = false
    /// Set by an interruption while scanning; the scan stays paused until the person taps Continue,
    /// even after the app is active again. The AR session keeps running so RoomPlan keeps its room.
    var heldPauseReason: PauseReason?
    var isThermalCritical = false
    var isThermalWarning = false
    var isTrackingUnavailable = false
    var needsRelocalization = false
    var relocalizationTimedOut = false
    var roomCaptureNeedsRestart = false
    var lastRoomCaptureError: String?
    /// The room in progress as RoomPlan last had it before failing; kept until the room is saved.
    var salvagedRoomJSON: Data?
    var isARSessionRunning = false
    var isIdleTimerDisabled = false

    /// Zero-based index of the room being captured, matching `RoomRecord.index` and `rooms/<n>.json`.
    var currentRoom: Int { completedRooms }

    var canStartNextRoom: Bool {
        activity == .betweenRooms && completedRooms < Self.maxRoomsPerStructure
    }

    var pauseReason: PauseReason? {
        if app == .background { return .backgrounded }
        if app == .inactive { return .appInactive }
        if isSessionInterrupted { return .sessionInterrupted }
        if let heldPauseReason { return heldPauseReason }
        if isThermalCritical { return .thermal }
        if isUserPaused { return .user }
        if isTrackingUnavailable { return .trackingLost }
        return nil
    }

    var phase: CapturePhase {
        switch activity {
        case .idle: .idle
        case .capturing: pausedPhase ?? .scanning(room: currentRoom)
        case .relocalizing: pausedPhase ?? .relocalizing(room: currentRoom)
        case .savingRoom(let finishScanAfterwards): finishScanAfterwards ? .finishing : .betweenRooms(completed: completedRooms)
        case .betweenRooms: .betweenRooms(completed: completedRooms)
        case .finishing: .finishing
        case .finished: .finished
        case .failed(let message): .failed(message: message)
        }
    }

    var isScanInProgress: Bool {
        switch activity {
        case .idle, .finished, .failed: false
        case .capturing, .relocalizing, .savingRoom, .betweenRooms, .finishing: true
        }
    }

    var isScanningRoom: Bool {
        switch activity {
        case .capturing, .relocalizing: true
        default: false
        }
    }

    var isRoomCaptureRunning: Bool {
        switch activity {
        case .capturing, .savingRoom, .relocalizing(roomCaptureRunning: true): true
        default: false
        }
    }

    var wantsARSessionRunning: Bool {
        guard isScanInProgress, app != .background, !isUserPaused, !isThermalCritical else { return false }
        guard needsRelocalization else { return true }
        if case .relocalizing = activity { return true }
        return false
    }

    /// A world map is only worth saving while tracking is aligned with the frame the rooms live in.
    var canCheckpoint: Bool {
        guard isARSessionRunning, !isTrackingUnavailable else { return false }
        switch activity {
        case .capturing, .savingRoom, .betweenRooms: return !needsRelocalization
        default: return false
        }
    }

    private var pausedPhase: CapturePhase? {
        pauseReason.map { .paused(room: currentRoom, reason: $0) }
    }
}
