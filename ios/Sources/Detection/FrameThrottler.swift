import Synchronization

/// Admits every `stride`-th frame, and none while a previous frame is still being processed.
nonisolated final class FrameThrottler: Sendable {
    private struct State {
        var framesSinceAdmitted = 0
        var isBusy = false
    }

    let stride: Int
    private let state = Mutex(State())

    init(stride: Int = 3) {
        precondition(stride >= 1, "stride must be at least 1")
        self.stride = stride
    }

    /// Returns true when the caller should process this frame; it must then call `finish()`.
    func admit() -> Bool {
        state.withLock { state in
            state.framesSinceAdmitted += 1
            guard !state.isBusy, state.framesSinceAdmitted >= stride else { return false }
            state.framesSinceAdmitted = 0
            state.isBusy = true
            return true
        }
    }

    func finish() {
        state.withLock { $0.isBusy = false }
    }
}
