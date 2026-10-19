import simd

nonisolated enum OverlayLabelContent: Sendable, Equatable {
    case measurement(kind: MeasurementKind, length: LengthText, status: FindingStatus?)
    case finding(section: String, status: FindingStatus)

    var status: FindingStatus? {
        switch self {
        case .measurement(_, _, let status): status
        case .finding(_, let status): status
        }
    }
}

/// A 2D label pinned to a point in the world.
nonisolated struct OverlayLabel: Sendable, Equatable, Identifiable {
    let id: String
    let content: OverlayLabelContent
    let anchor: SIMD3<Float>
    let span: [SIMD3<Float>]
    let priority: Int
}

nonisolated enum OverlayLabelBuilder {
    static func labels(measurements: [LiveMeasurement], findings: [Finding], elements: [LiveElement]) -> [OverlayLabel] {
        let statusBySubject = worstStatusBySubject(findings)
        let measured = measurements.map { measurementLabel($0, status: statusBySubject[$0.subjectID]) }
        let measuredSubjects = Set(measurements.map(\.subjectID))
        let badges = badgeLabels(
            findings: findings.filter { !measuredSubjects.contains($0.subjectID) },
            elements: elements
        )
        return measured + badges
    }

    static func worstStatusBySubject(_ findings: [Finding]) -> [String: FindingStatus] {
        Dictionary(grouping: findings.filter { severity(of: $0.status) > 0 }, by: \.subjectID)
            .compactMapValues { group in group.map(\.status).max { severity(of: $0) < severity(of: $1) } }
    }

    static func severity(of status: FindingStatus?) -> Int {
        switch status {
        case .fail: 3
        case .needsInfo: 2
        case .pass: 1
        case .notApplicable, nil: 0
        }
    }

    private static func measurementLabel(_ measurement: LiveMeasurement, status: FindingStatus?) -> OverlayLabel {
        OverlayLabel(
            id: measurement.id,
            content: .measurement(kind: measurement.kind, length: LengthText(meters: measurement.meters), status: status),
            anchor: measurement.anchor,
            span: measurement.span,
            priority: severity(of: status) * 10 + kindPriority(measurement.kind)
        )
    }

    private static func kindPriority(_ kind: MeasurementKind) -> Int {
        switch kind {
        case .passageWidth: 3
        case .clearWidth: 2
        case .topHeight: 1
        }
    }

    private static func badgeLabels(findings: [Finding], elements: [LiveElement]) -> [OverlayLabel] {
        let elementsByID = Dictionary(elements.map { ($0.id, $0) }) { first, _ in first }
        return Dictionary(grouping: findings, by: \.subjectID).compactMap { subjectID, group in
            guard let element = elementsByID[subjectID],
                  let worst = group.filter({ severity(of: $0.status) > 0 }).max(by: { severity(of: $0.status) < severity(of: $1.status) })
            else { return nil }
            return OverlayLabel(
                id: "finding:\(subjectID)",
                content: .finding(section: worst.section, status: worst.status),
                anchor: PlanGeometry.worldPoint(SIMD3(0, element.dimensions.y / 2, 0), transform: element.transform),
                span: [],
                priority: severity(of: worst.status) * 10
            )
        }
    }
}
