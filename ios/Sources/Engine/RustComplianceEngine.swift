import Foundation
import SPEngineKit

nonisolated enum RulepackFile: String, CaseIterable {
    case metrics
    case ada2010
    case cbc11b
}

nonisolated enum ComplianceEngineError: Error, Equatable {
    case missingRulepack(String)
    case unreadableRoom
    case engine(String)
}

/// Evaluates rooms as they are finished, then the whole scan, with the shared Rust engine.
nonisolated protocol RoomComplianceEvaluating: Sendable {
    func evaluateRoom(capturedRoomJSON: Data) async throws -> [Finding]
    func evaluateScan() async throws -> ComplianceReport
}

nonisolated struct ComplianceReport: Sendable, Equatable {
    let findings: [Finding]
    let governingFailures: Int
    let governingNeedsInfo: Int
    let governingPasses: Int
    let reportJSON: String
}

/// The engine is not thread-safe per scene, so one actor owns it and every call runs off the
/// main actor.
actor RustComplianceEngine: RoomComplianceEvaluating {
    private let engine: SpEngine

    init(bundle: Bundle = .main) throws {
        let catalog = try Self.load(.metrics, from: bundle)
        let rulepacks = try [RulepackFile.ada2010, .cbc11b].map { try Self.load($0, from: bundle) }
        do {
            engine = try SpEngine(catalogJson: catalog, rulepackJsons: rulepacks)
        } catch {
            throw ComplianceEngineError.engine(String(describing: error))
        }
    }

    func evaluateRoom(capturedRoomJSON: Data) throws -> [Finding] {
        guard let json = String(data: capturedRoomJSON, encoding: .utf8) else {
            throw ComplianceEngineError.unreadableRoom
        }
        do {
            return try engine.updateRoomplanRoom(capturedRoomJson: json).map(Finding.init)
        } catch {
            throw ComplianceEngineError.engine(String(describing: error))
        }
    }

    func evaluateScan() -> ComplianceReport {
        let report = engine.evaluateAll()
        return ComplianceReport(
            findings: report.jurisdictions.flatMap(\.findings).map(Finding.init),
            governingFailures: Int(report.governingCounts.fail),
            governingNeedsInfo: Int(report.governingCounts.needsInfo),
            governingPasses: Int(report.governingCounts.pass),
            reportJSON: engine.reportJson()
        )
    }

    private nonisolated static func load(_ file: RulepackFile, from bundle: Bundle) throws -> String {
        guard let url = bundle.url(forResource: file.rawValue, withExtension: "json"),
              let text = try? String(contentsOf: url, encoding: .utf8)
        else {
            throw ComplianceEngineError.missingRulepack(file.rawValue)
        }
        return text
    }
}

extension Finding {
    nonisolated init(_ finding: SpFinding) {
        self.init(
            ruleID: finding.ruleId,
            jurisdiction: Jurisdiction(rawValue: finding.jurisdiction) ?? .ada2010,
            section: finding.section,
            subjectID: finding.subjectId,
            status: FindingStatus(finding.status),
            measured: finding.measured.flatMap(MeasuredValue.init),
            required: finding.required,
            message: finding.message
        )
    }
}

extension FindingStatus {
    nonisolated init(_ status: SpStatus) {
        switch status {
        case .pass: self = .pass
        case .fail: self = .fail
        case .needsInfo: self = .needsInfo
        case .notApplicable: self = .notApplicable
        }
    }
}

extension MeasuredValue {
    nonisolated init?(_ measured: SpMeasured) {
        guard let value = measured.value ?? measured.lo else { return nil }
        self.init(value: value, unit: measured.unit)
    }
}
