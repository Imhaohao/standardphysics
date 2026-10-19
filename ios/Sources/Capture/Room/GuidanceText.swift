import Foundation
import RoomPlan

nonisolated enum ScanInstruction: Sendable, Equatable {
    case normal
    case moveCloserToWall
    case moveAwayFromWall
    case slowDown
    case turnOnLight
    case lowTexture

    init(_ instruction: RoomCaptureSession.Instruction) {
        switch instruction {
        case .moveCloseToWall: self = .moveCloserToWall
        case .moveAwayFromWall: self = .moveAwayFromWall
        case .slowDown: self = .slowDown
        case .turnOnLight: self = .turnOnLight
        case .lowTexture: self = .lowTexture
        case .normal: self = .normal
        @unknown default: self = .normal
        }
    }

    var text: String? {
        switch self {
        case .normal: nil
        case .moveCloserToWall: "Move closer to the wall"
        case .moveAwayFromWall: "Step back from the wall"
        case .slowDown: "Slow down"
        case .turnOnLight: "Turn on more lights"
        case .lowTexture: "Aim at something with more detail, like a corner or a shelf"
        }
    }
}

nonisolated struct GuidanceInput: Sendable, Equatable {
    var phase: CapturePhase
    var instruction: ScanInstruction = .normal
    var isThermalWarning = false
    var relocalizationTimedOut = false
    var lastRoomCaptureError: String?
}

/// One short line for the person holding the phone. The capture state outranks RoomPlan's coaching.
nonisolated enum GuidanceText {
    static func message(for input: GuidanceInput) -> String? {
        switch input.phase {
        case .relocalizing: relocalizingMessage(timedOut: input.relocalizationTimedOut)
        case .paused(_, let reason): pausedMessage(reason)
        case .scanning: scanningMessage(input)
        default: nil
        }
    }

    private static func relocalizingMessage(timedOut: Bool) -> String {
        timedOut
            ? "Still can't find where you stopped. You can start this room again."
            : "Stand where the photo was taken and point the camera the same way"
    }

    private static func pausedMessage(_ reason: PauseReason) -> String? {
        switch reason {
        case .thermal: "Your phone is too hot. Let it cool down and the scan will carry on."
        case .trackingLost: "Point the camera at the room so it can find its place"
        case .sessionInterrupted: "Waiting for the camera to come back"
        case .appInactive, .backgrounded, .user: nil
        }
    }

    private static func scanningMessage(_ input: GuidanceInput) -> String? {
        if let text = input.instruction.text { return text }
        if input.lastRoomCaptureError != nil { return "That room didn't save, so scan it once more" }
        if input.isThermalWarning { return "Your phone is getting warm. Keep moving steadily." }
        return nil
    }
}
