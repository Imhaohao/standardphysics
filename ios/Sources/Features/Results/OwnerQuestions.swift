import Foundation

/// One thing to ask the owner about one subject. Every finding that waits on the same subject and
/// metric (the ADA and CBC twins, or two sections that read the same fact) shares it.
nonisolated struct OwnerQuestion: Sendable, Equatable, Identifiable {
    let subjectID: String
    let ask: FindingAsk

    var id: String { OwnerQuestions.key(subjectID: subjectID, metric: ask.metric) }
}

nonisolated enum OwnerQuestions {
    private static let unitNames = ["in": "inches", "lbf": "pounds of force", "ft": "feet", "s": "seconds", "deg": "degrees", "%": "percent"]

    static func key(subjectID: String, metric: String) -> String {
        "\(subjectID)#\(metric)"
    }

    /// The question an open outcome asks, when its findings carry one this app can collect.
    static func question(for outcome: RuleOutcome) -> OwnerQuestion? {
        guard outcome.isQuestion, let ask = outcome.governing.ask ?? outcome.federal?.ask ?? outcome.california?.ask,
              ask.valueType != .unsupported else { return nil }
        return OwnerQuestion(subjectID: outcome.subjectID, ask: ask)
    }

    /// Keeps the first outcome for each question, so it is asked once; everything else passes through.
    static func deduplicated(_ outcomes: [RuleOutcome]) -> [RuleOutcome] {
        var asked = Set<String>()
        return outcomes.filter { outcome in
            guard let question = question(for: outcome) else { return true }
            return asked.insert(question.id).inserted
        }
    }

    static func answer(to question: OwnerQuestion, in answers: [OwnerAnswer]) -> OwnerAnswer? {
        answers.first { $0.key == question.id }
    }

    /// Sets or, with nil, clears the owner's answer to `question`.
    static func setting(
        _ value: AnswerValue?, for question: OwnerQuestion, in answers: [OwnerAnswer], source: String? = nil
    ) -> [OwnerAnswer] {
        let others = answers.filter { $0.key != question.id }
        guard let value else { return others }
        let unit = question.ask.unit.isEmpty ? nil : question.ask.unit
        return others + [OwnerAnswer(subjectID: question.subjectID, metric: question.ask.metric, value: value, unit: unit, source: source)]
    }

    /// Every answer the owner gave by hand, plus a `null` for the one just cleared, so the server
    /// drops it too. Answers read from a photo already live on the server as photo answers.
    static func updates(for answers: [OwnerAnswer], clearing cleared: OwnerQuestion?) -> [AnswerUpdate] {
        let current = answers.filter { !$0.isFromPhoto }.map { AnswerUpdate(subjectID: $0.subjectID, metric: $0.metric, value: $0.value) }
        guard let cleared else { return current }
        return current + [AnswerUpdate(subjectID: cleared.subjectID, metric: cleared.ask.metric, value: nil)]
    }

    /// Accepts "4.5" and "4,5"; an integer question rounds to a whole number.
    static func numberValue(from text: String, valueType: AskValueType) -> AnswerValue? {
        let normalized = text.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: ".")
        guard let number = Double(normalized), number.isFinite else { return nil }
        return .number(valueType == .integer ? number.rounded() : number)
    }

    static func text(for value: AnswerValue?) -> String {
        switch value {
        case .number(let number): MeasurementFormat.trimmed(number)
        case .text(let text): text
        case .bool, nil: ""
        }
    }

    static func unitName(_ unit: String) -> String {
        unitNames[unit] ?? unit
    }

    /// "full_service" reads as "Full service".
    static func optionTitle(_ option: String) -> String {
        let spaced = option.replacingOccurrences(of: "_", with: " ")
        return spaced.prefix(1).uppercased() + spaced.dropFirst()
    }
}
