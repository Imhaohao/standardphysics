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
    func evaluateRoom(capturedRoomJSON: Data, detectedObjects: [DetectedObject]) async throws -> [Finding]
    /// Answers the owner gave, added to the scene as owner observations before `evaluateScan`.
    func addOwnerAnswers(_ answers: [OwnerAnswer]) async throws
    func evaluateScan() async throws -> ComplianceReport
}

extension RoomComplianceEvaluating {
    nonisolated func evaluateRoom(capturedRoomJSON: Data) async throws -> [Finding] {
        try await evaluateRoom(capturedRoomJSON: capturedRoomJSON, detectedObjects: [])
    }

    nonisolated func addOwnerAnswers(_ answers: [OwnerAnswer]) async throws {}
}

nonisolated struct ComplianceReport: Sendable, Equatable {
    let findings: [Finding]
    /// Room id for each finding id, where the engine knows it.
    let findingRooms: [String: String]
    let sceneJSON: String
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

    /// Detector objects join the first room of the capture before it is checked.
    func evaluateRoom(capturedRoomJSON: Data, detectedObjects: [DetectedObject]) throws -> [Finding] {
        guard let json = String(data: capturedRoomJSON, encoding: .utf8) else {
            throw ComplianceEngineError.unreadableRoom
        }
        do {
            guard !detectedObjects.isEmpty else {
                return try engine.updateRoomplanRoom(capturedRoomJson: json).map(Finding.init)
            }
            let rooms = try importRoomplan(json: json)
            let extraObjects = detectedObjects.map(SpObject.init)
            return rooms.enumerated().flatMap { index, room in
                var updated = room
                if index == 0 { updated.objects += extraObjects }
                return engine.updateRoom(room: updated)
            }.map(Finding.init)
        } catch {
            throw ComplianceEngineError.engine(String(describing: error))
        }
    }

    func sceneJSON() -> String {
        engine.sceneJson()
    }

    func addOwnerAnswers(_ answers: [OwnerAnswer]) {
        guard !answers.isEmpty else { return }
        engine.addObservations(observations: answers.map(SpObservation.init))
    }

    func evaluateScan() -> ComplianceReport {
        let report = engine.evaluateAll()
        let engineFindings = report.jurisdictions.flatMap(\.findings)
        let findings = engineFindings.map(Finding.init)
        let rooms = zip(findings, engineFindings).compactMap { finding, source in
            source.roomId.map { (finding.id, $0) }
        }
        return ComplianceReport(
            findings: findings,
            findingRooms: Dictionary(rooms, uniquingKeysWith: { first, _ in first }),
            sceneJSON: engine.sceneJson(),
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
            jurisdiction: Jurisdiction(rawValue: finding.jurisdiction) ?? .system,
            section: finding.section,
            subjectID: finding.subjectId,
            status: FindingStatus(finding.status),
            measured: finding.measured.flatMap(MeasuredValue.init),
            required: finding.required,
            message: finding.message,
            title: finding.title.isEmpty ? nil : finding.title,
            severity: FindingSeverity(rawValue: finding.severity),
            counterpartRuleID: finding.counterpart,
            range: finding.measured.flatMap(MeasuredRange.init),
            ask: finding.ask.map(FindingAsk.init)
        )
    }
}

extension FindingAsk {
    nonisolated init(_ ask: SpAsk) {
        self.init(
            metric: ask.metric,
            prompt: ask.prompt,
            valueType: AskValueType(rawValue: ask.valueType) ?? .unsupported,
            unit: ask.unit,
            options: ask.options,
            photo: ask.photo
        )
    }
}

extension SpObservation {
    /// One answer per subject and metric, so the id is stable and a second answer replaces the first.
    nonisolated init(_ answer: OwnerAnswer) {
        self.init(
            id: "owner.\(answer.subjectID).\(answer.metric)",
            subjectId: answer.subjectID,
            metric: answer.metric,
            value: SpObservationValue(answer.value),
            unit: answer.unit,
            source: .owner,
            confidence: 1
        )
    }
}

extension SpObservationValue {
    nonisolated init(_ value: AnswerValue) {
        switch value {
        case .bool(let flag): self = .bool(value: flag)
        case .number(let number): self = .number(value: number)
        case .text(let text): self = .text(value: text)
        }
    }
}

extension SpObject {
    nonisolated init(_ object: DetectedObject) {
        self.init(
            id: object.id,
            category: object.category,
            center: SpVec3(x: object.center.x, y: object.center.y, z: object.center.z),
            size: SpVec3(x: object.size.x, y: object.size.y, z: object.size.z),
            yaw: object.yaw,
            topHeight: object.topHeight,
            confidence: object.confidence,
            source: .detector,
            attributes: ["detector_label": object.label, "detector_hits": String(object.hits)]
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

extension MeasuredRange {
    nonisolated init?(_ measured: SpMeasured) {
        guard let lo = measured.lo, let hi = measured.hi else { return nil }
        self.init(lo: lo, hi: hi, unit: measured.unit)
    }
}

extension MeasuredValue {
    nonisolated init?(_ measured: SpMeasured) {
        guard let value = measured.value ?? measured.lo else { return nil }
        self.init(value: value, unit: measured.unit)
    }
}
