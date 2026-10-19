import ARKit
import Foundation

nonisolated enum ARHostEvent: Sendable, Equatable {
    case tracking(TrackingStatus)
    case interrupted
    case interruptionEnded
    case checkpointDue
    case failed(message: String)
}

nonisolated struct Checkpoint: Sendable, Equatable {
    let worldMap: Data
    let snapshotJPEG: Data?
}

/// Decides when the periodic world-map checkpoint is due. The first well-mapped frame
/// checkpoints at once so even a short walk has something to resume from.
nonisolated struct CheckpointClock: Sendable {
    static let interval: TimeInterval = 12

    private var lastCheckpoint: TimeInterval?

    mutating func isDue(at timestamp: TimeInterval, isMappingGood: Bool) -> Bool {
        guard isMappingGood else { return false }
        if let lastCheckpoint, timestamp - lastCheckpoint < Self.interval { return false }
        lastCheckpoint = timestamp
        return true
    }
}

nonisolated extension TrackingStatus {
    init(_ state: ARCamera.TrackingState) {
        switch state {
        case .normal: self = .normal
        case .notAvailable: self = .notAvailable
        case .limited(let reason): self = .limited(LimitedTrackingReason(reason))
        }
    }
}

nonisolated extension LimitedTrackingReason {
    init(_ reason: ARCamera.TrackingState.Reason) {
        switch reason {
        case .relocalizing: self = .relocalizing
        case .excessiveMotion: self = .excessiveMotion
        case .insufficientFeatures: self = .insufficientFeatures
        case .initializing: self = .initializing
        @unknown default: self = .initializing
        }
    }
}

nonisolated extension ARFrame.WorldMappingStatus {
    var isGoodEnoughToSave: Bool { self == .mapped || self == .extending }
}
