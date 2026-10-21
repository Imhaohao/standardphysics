import Foundation

nonisolated enum ProcessingStage: Int, CaseIterable, Sendable, Comparable {
    case uploading
    case assembling
    case checking
    case writing

    static func < (lhs: ProcessingStage, rhs: ProcessingStage) -> Bool {
        lhs.rawValue < rhs.rawValue
    }

    var title: String {
        switch self {
        case .uploading: "Sending the last of your scan"
        case .assembling: "Joining your rooms into one floor plan"
        case .checking: "Checking every item against both codes"
        case .writing: "Writing up what to fix"
        }
    }
}

nonisolated struct ProcessingUpdate: Sendable, Equatable {
    let stage: ProcessingStage
    /// Overall progress, 0...1.
    let fraction: Double
}

/// Uploads a finished scan and returns the checked report. The server lane provides the real
/// one; `PreviewScanProcessor` stands in until then.
protocol ScanProcessing: AnyObject {
    func process(_ manifest: ScanManifest, onUpdate: @escaping (ProcessingUpdate) -> Void) async throws -> ScanReport
}

/// Checks a report checked on this phone again with the owner's answers.
protocol ReportRechecking: AnyObject {
    func recheck(scanID: UUID, answers: [OwnerAnswer]) async throws -> ScanReport
}

extension OnDeviceScanProcessor: ReportRechecking {}

final class PreviewScanProcessor: ScanProcessing {
    private let stepDelay: Duration
    private let report: (ScanManifest) -> ScanReport

    init(stepDelay: Duration = .milliseconds(900), report: @escaping (ScanManifest) -> ScanReport = SampleData.report(for:)) {
        self.stepDelay = stepDelay
        self.report = report
    }

    func process(_ manifest: ScanManifest, onUpdate: @escaping (ProcessingUpdate) -> Void) async throws -> ScanReport {
        let stages = ProcessingStage.allCases
        for (index, stage) in stages.enumerated() {
            onUpdate(ProcessingUpdate(stage: stage, fraction: Double(index) / Double(stages.count)))
            try await Task.sleep(for: stepDelay)
        }
        onUpdate(ProcessingUpdate(stage: .writing, fraction: 1))
        return report(manifest)
    }
}
