import Foundation

/// A requirement read from a finding's `required` text, such as "≤ 34 in" or "17–18 in".
nonisolated enum RequiredBound: Equatable, Sendable {
    case atMost(Double)
    case atLeast(Double)
    case between(Double, Double)

    private static let maximumMarkers = ["≤", "<=", "<", "max", "at most", "no more than", "no higher than"]
    private static let minimumMarkers = ["≥", ">=", ">", "min", "at least", "no less than", "no lower than"]

    static func parse(_ text: String) -> RequiredBound? {
        let numbers = text.matches(of: /[0-9]+(?:\.[0-9]+)?/).compactMap { Double($0.output) }
        let lowered = text.lowercased()
        if numbers.count >= 2 { return .between(min(numbers[0], numbers[1]), max(numbers[0], numbers[1])) }
        guard let value = numbers.first else { return nil }
        if maximumMarkers.contains(where: lowered.hasPrefix) { return .atMost(value) }
        if minimumMarkers.contains(where: lowered.hasPrefix) { return .atLeast(value) }
        return nil
    }

    /// True when every value that satisfies `self` also satisfies `other`, and `other` allows more.
    func isStricter(than other: RequiredBound) -> Bool {
        switch (self, other) {
        case let (.atMost(mine), .atMost(theirs)): mine < theirs
        case let (.atLeast(mine), .atLeast(theirs)): mine > theirs
        case let (.between(low, high), .between(otherLow, otherHigh)):
            low >= otherLow && high <= otherHigh && (low, high) != (otherLow, otherHigh)
        default: false
        }
    }
}

extension FindingStatus {
    nonisolated var severity: Int {
        switch self {
        case .fail: 3
        case .needsInfo: 2
        case .pass: 1
        case .notApplicable: 0
        }
    }
}

/// One requirement on one thing, with the federal and California findings side by side and
/// the one that governs picked out.
nonisolated struct RuleOutcome: Sendable, Equatable, Identifiable {
    let subjectID: String
    let section: String
    let federal: Finding?
    let california: Finding?
    let governing: Finding

    var id: String { isOwnerQuestion ? governing.id : "\(subjectID)#\(section)" }
    var status: FindingStatus { governing.status }
    /// Something only the owner can settle, such as an object we could not identify. It asks
    /// for a check and never counts as a code violation.
    var isOwnerQuestion: Bool { governing.isOwnerQuestion }
    var hasBothJurisdictions: Bool { federal != nil && california != nil }

    func governs(_ finding: Finding) -> Bool {
        governing == finding
    }
}

nonisolated enum RuleComparison {
    /// In California both codes apply, so the stricter result is the one to meet. A finding that
    /// fails beats one that passes; between equal results the tighter limit wins; on a tie the
    /// state code governs.
    static func governing(federal: Finding?, california: Finding?) -> Finding? {
        guard let federal else { return california }
        guard let california else { return federal }
        if federal.status.severity != california.status.severity {
            return federal.status.severity > california.status.severity ? federal : california
        }
        return federalIsStricter(federal, california) ? federal : california
    }

    private static func federalIsStricter(_ federal: Finding, _ california: Finding) -> Bool {
        guard let federalBound = RequiredBound.parse(federal.required),
              let californiaBound = RequiredBound.parse(california.required) else { return false }
        return federalBound.isStricter(than: californiaBound)
    }

    /// "11B-904.4.1", "§904.4.1" and "904.4.1" all name the same requirement.
    static func sharedSection(_ section: String) -> String {
        var trimmed = section.trimmingCharacters(in: .whitespaces)
        for prefix in ["§", "11B-", "11b-"] where trimmed.hasPrefix(prefix) {
            trimmed.removeFirst(prefix.count)
        }
        return trimmed
    }

    static func outcomes(from findings: [Finding]) -> [RuleOutcome] {
        codeOutcomes(from: findings.filter { !$0.isOwnerQuestion })
            + findings.filter(\.isOwnerQuestion).map(ownerQuestion)
    }

    private static func ownerQuestion(_ finding: Finding) -> RuleOutcome {
        RuleOutcome(subjectID: finding.subjectID, section: finding.section, federal: nil, california: nil, governing: finding)
    }

    private static func codeOutcomes(from findings: [Finding]) -> [RuleOutcome] {
        var order: [String] = []
        var pairs: [String: (federal: Finding?, california: Finding?)] = [:]
        for finding in findings {
            let key = "\(finding.subjectID)#\(sharedSection(finding.section))"
            if pairs[key] == nil { order.append(key) }
            var pair = pairs[key] ?? (nil, nil)
            if finding.jurisdiction == .ada2010 { pair.federal = finding } else { pair.california = finding }
            pairs[key] = pair
        }
        return order.compactMap { key in
            guard let pair = pairs[key], let governing = governing(federal: pair.federal, california: pair.california) else { return nil }
            return RuleOutcome(subjectID: governing.subjectID, section: sharedSection(governing.section), federal: pair.federal, california: pair.california, governing: governing)
        }
    }
}

nonisolated enum Citation {
    static func text(for finding: Finding) -> String {
        let section = RuleComparison.sharedSection(finding.section)
        switch finding.jurisdiction {
        case .ada2010: return "ADA 2010 §\(section)"
        case .cbc11b: return "CBC 11B-\(section)"
        case .system: return "Standard Physics check"
        }
    }

    static func jurisdictionName(_ jurisdiction: Jurisdiction) -> String {
        switch jurisdiction {
        case .ada2010: "Federal"
        case .cbc11b: "California"
        case .system: "Standard Physics"
        }
    }
}
