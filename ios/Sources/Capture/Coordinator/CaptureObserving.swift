import Foundation

/// Points in a scan that other parts of the app react to, after the journal has them on disk.
nonisolated enum CaptureMilestone: Sendable, Equatable {
    case started(ScanManifest)
    case resumed(ScanManifest)
    case roomSaved(index: Int, manifest: ScanManifest)
    case meshSaved(ScanManifest)
    case discarded(scanID: UUID)
}

/// What an observer may hand back to the capture flow.
@MainActor
protocol CaptureLinking: AnyObject {
    /// Saves the key for creating the scan on the server, before the first attempt.
    func recordRemoteCreateKey(_ key: String, forScan scanID: UUID) async
    /// Saves the server's id for the scan into its manifest straight away.
    func recordRemoteScanID(_ remoteScanID: String, forScan scanID: UUID) async
    func mergeServerFindings(_ findings: [Finding])
}

@MainActor
protocol CaptureObserving: AnyObject {
    func capture(_ link: any CaptureLinking, reached milestone: CaptureMilestone)
}

nonisolated enum FindingMerge {
    /// The server has the whole space and the labelled objects, so where both have checked the
    /// same rule on the same thing, its answer replaces the phone's.
    static func preferringServer(onDevice: [Finding], server: [Finding]) -> [Finding] {
        let serverIDs = Set(server.map(\.id))
        return onDevice.filter { !serverIDs.contains($0.id) } + server
    }

    /// Newer findings replace older ones with the same id; order of first appearance is kept.
    static func upsert(_ incoming: [Finding], into existing: [Finding]) -> [Finding] {
        let latest = Dictionary(incoming.map { ($0.id, $0) }, uniquingKeysWith: { _, newer in newer })
        let kept = existing.map { latest[$0.id] ?? $0 }
        let existingIDs = Set(existing.map(\.id))
        var added: [Finding] = []
        var seen = existingIDs
        for finding in incoming where !seen.contains(finding.id) {
            seen.insert(finding.id)
            added.append(latest[finding.id] ?? finding)
        }
        return kept + added
    }
}
