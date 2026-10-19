import Foundation

/// Uses the server's assessment when the owner is signed in and the server answers, and the
/// phone's own engine otherwise, so a scan is never stuck waiting on a network.
final class PreferredScanProcessor: ScanProcessing {
    private let remote: (any ScanProcessing)?
    private let local: any ScanProcessing
    private let isSignedIn: () -> Bool

    init(remote: (any ScanProcessing)?, local: any ScanProcessing, isSignedIn: @escaping () -> Bool) {
        self.remote = remote
        self.local = local
        self.isSignedIn = isSignedIn
    }

    func process(_ manifest: ScanManifest, onUpdate: @escaping (ProcessingUpdate) -> Void) async throws -> ScanReport {
        guard let remote, isSignedIn() else {
            return try await local.process(manifest, onUpdate: onUpdate)
        }
        do {
            return try await remote.process(manifest, onUpdate: onUpdate)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            return try await local.process(manifest, onUpdate: onUpdate)
        }
    }
}
