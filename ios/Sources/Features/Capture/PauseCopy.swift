import Foundation

nonisolated struct PauseCopy: Equatable, Sendable {
    let title: String
    let message: String
    let systemImage: String

    init(_ reason: PauseReason) {
        switch reason {
        case .user:
            self.init(title: "Scan paused", message: "Tap Continue when you're ready.", systemImage: "pause.fill")
        case .appInactive:
            self.init(title: "Scan paused", message: "We paused while Control Center or a notification was open. Tap Continue when you're ready.", systemImage: "pause.fill")
        case .backgrounded:
            self.init(title: "Scan paused", message: "We paused when you left the app and saved everything so far. Tap Continue when you're ready.", systemImage: "pause.fill")
        case .sessionInterrupted:
            self.init(title: "Scan paused", message: "Another app or a call needed the camera, so we paused. Tap Continue when you're ready.", systemImage: "phone.fill")
        case .trackingLost:
            self.init(title: "The camera lost its place", message: "Point it at something with detail, like a doorframe or a shelf, then tap Continue.", systemImage: "camera.metering.unknown")
        case .thermal:
            self.init(title: "Your iPhone needs to cool down", message: "It got too warm to keep measuring accurately. Rest it out of the sun for a few minutes, then tap Continue.", systemImage: "thermometer.high")
        }
    }

    private init(title: String, message: String, systemImage: String) {
        self.title = title
        self.message = message
        self.systemImage = systemImage
    }
}
