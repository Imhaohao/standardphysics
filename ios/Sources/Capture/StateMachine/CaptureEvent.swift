import Foundation

nonisolated enum AppActivity: Sendable, Equatable {
    case active
    case inactive
    case background
}

nonisolated enum LimitedTrackingReason: Sendable, Equatable {
    case initializing
    case relocalizing
    case excessiveMotion
    case insufficientFeatures
}

nonisolated enum TrackingStatus: Sendable, Equatable {
    case normal
    case limited(LimitedTrackingReason)
    case notAvailable
}

nonisolated enum ThermalLevel: Sendable, Equatable {
    case nominal
    case fair
    case serious
    case critical
}

/// What survived on disk when the app comes back after being killed.
nonisolated struct ResumePoint: Sendable, Equatable {
    let completedRooms: Int
    let hasWorldMap: Bool
    let wasBetweenRooms: Bool
}

nonisolated enum CaptureEvent: Sendable, Equatable {
    case start
    case resume(ResumePoint)
    case appActivity(AppActivity)
    case appWillResignActive
    case sessionInterrupted
    case sessionInterruptionEnded
    case sessionFailed(message: String)
    case tracking(TrackingStatus)
    case thermal(ThermalLevel)
    case checkpointDue
    case roomCaptureEnded(roomJSON: Data)
    case roomCaptureFailed(message: String)
    case userPause
    case userContinue
    case finishRoom
    case nextRoom
    case relocalized
    case relocalizationTimedOut
    case restartRoom
    case finishScan
    case exportFinished
    case exportFailed(message: String)
    case discard
}

nonisolated enum ARRunMode: Sendable, Equatable {
    /// Run the world-tracking configuration without resetting, keeping the current map.
    case continueExisting
    /// Run with the journal's saved world map as `initialWorldMap`.
    case relocalize
    /// Reset tracking and anchors: a new coordinate frame.
    case fresh
}

nonisolated enum CaptureEffect: Sendable, Equatable {
    case runARSession(ARRunMode)
    case pauseARSession
    case startRoomCapture(room: Int)
    case finishRoomCapture
    case cancelRoomCapture
    case saveCheckpoint
    case persistRoom(index: Int, roomJSON: Data)
    case exportMesh
    case exportStructure
    case persistManifest
    case setIdleTimerDisabled(Bool)
    case startRelocalizationTimer
    case cancelRelocalizationTimer
    case deleteScan
}
