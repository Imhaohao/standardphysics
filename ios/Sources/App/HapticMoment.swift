import SwiftUI

/// The three points in a scan worth feeling: a room saved, the scan handed off for checking,
/// and the report ready to read.
enum HapticMoment: Equatable {
    case roomFinished
    case scanFinished
    case reportReady

    static func forRoute(from old: AppRoute, to new: AppRoute) -> HapticMoment? {
        switch (old, new) {
        case (.capture, .processing): .scanFinished
        case (.processing, .results): .reportReady
        default: nil
        }
    }

    /// Only a room the owner just finished; landing between rooms on resume is not one.
    static func forPhase(from old: CapturePhase, to new: CapturePhase) -> HapticMoment? {
        guard case .betweenRooms = new else { return nil }
        switch old {
        case .scanning, .paused: return .roomFinished
        default: return nil
        }
    }

    var feedback: SensoryFeedback {
        switch self {
        case .roomFinished: .success
        case .scanFinished: .impact(weight: .medium)
        case .reportReady: .success
        }
    }
}
