import Foundation
import UIKit

/// The slice of `UIApplication` the capture flow drives.
protocol CaptureApplication: AnyObject {
    var isIdleTimerDisabled: Bool { get set }
    /// Asks for a little background time so a checkpoint started while resigning can finish.
    func beginProtectedWork(named name: String) -> BackgroundWorkToken
    func endProtectedWork(_ token: BackgroundWorkToken)
}

final class BackgroundWorkToken {
    var identifier: UIBackgroundTaskIdentifier = .invalid
}

extension UIApplication: CaptureApplication {
    func beginProtectedWork(named name: String) -> BackgroundWorkToken {
        let token = BackgroundWorkToken()
        token.identifier = beginBackgroundTask(withName: name) { [token] in
            UIApplication.shared.endProtectedWork(token)
        }
        return token
    }

    func endProtectedWork(_ token: BackgroundWorkToken) {
        guard token.identifier != .invalid else { return }
        endBackgroundTask(token.identifier)
        token.identifier = .invalid
    }
}

struct CaptureDependencies {
    var journal: any ScanStore
    var host: any ARSessionHosting
    var scanner: any RoomScanning
    var merger: any StructureMerging
    var application: any CaptureApplication
    var notificationCenter = NotificationCenter.default
    var thermalState: () -> ProcessInfo.ThermalState = { ProcessInfo.processInfo.thermalState }
    var relocalizationTimeout = Duration.seconds(45)
    var sleep: @Sendable (Duration) async throws -> Void = { try await Task.sleep(for: $0) }

    static func live() -> CaptureDependencies {
        let host = ARSessionHost()
        return CaptureDependencies(
            journal: FileScanJournal(),
            host: host,
            scanner: RoomScanner(arSession: host.session),
            merger: StructureMerger(),
            application: UIApplication.shared
        )
    }
}

nonisolated extension ThermalLevel {
    init(_ state: ProcessInfo.ThermalState) {
        switch state {
        case .nominal: self = .nominal
        case .fair: self = .fair
        case .serious: self = .serious
        case .critical: self = .critical
        @unknown default: self = .serious
        }
    }
}
