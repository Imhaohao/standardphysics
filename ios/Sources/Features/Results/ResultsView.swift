import SwiftUI

struct ResultsView: View {
    @Environment(AppModel.self) private var model
    let reportID: UUID

    var body: some View {
        ZStack {
            PaperBackground()
            if let report = model.report(id: reportID) {
                ScrollView {
                    VStack(alignment: .leading, spacing: Theme.Spacing.xl) {
                        ResultsHeader(report: report) { model.goHome() }
                        if let notice = model.notice {
                            NoticeBanner(message: notice) { model.dismissNotice() }
                        }
                        ForEach(ReportGrouping.sections(for: report)) { section in
                            RoomSectionView(section: section, reportID: reportID)
                        }
                    }
                    .padding(Theme.Spacing.m)
                    .padding(.bottom, Theme.Spacing.xl)
                    .frame(maxWidth: Theme.Size.readable, alignment: .leading)
                }
                .scrollDismissesKeyboard(.interactively)
            }
        }
    }
}

/// Something that didn't go through, with a way to put it away.
struct NoticeBanner: View {
    let message: String
    let onDismiss: () -> Void

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s) {
            Image(systemName: "exclamationmark.circle.fill")
                .foregroundStyle(Theme.Palette.problem)
                .accessibilityHidden(true)
            Text(message)
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: Theme.Spacing.s)
            Button("Dismiss", action: onDismiss)
                .buttonStyle(InkButtonStyle(variant: .quiet, height: Theme.Size.compactControl))
        }
        .padding(.leading, Theme.Spacing.s + 4)
        .background(RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous).fill(Theme.Palette.problemWash))
        .accessibilityElement(children: .combine)
    }
}

private struct ResultsHeader: View {
    let report: ScanReport
    let onBack: () -> Void

    var body: some View {
        let summary = ReportGrouping.summary(for: report)
        VStack(alignment: .leading, spacing: Theme.Spacing.l) {
            BackButton(title: "Your scans", action: onBack)
            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                Text(report.name)
                    .font(Theme.Typography.title)
                    .foregroundStyle(Theme.Palette.ink)
                Text(checkedLine)
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Palette.inkMuted)
            }
            FixCount(count: summary.toFix)
            HStack(spacing: Theme.Spacing.s) {
                if summary.questions > 0 {
                    StatusPill(tone: .needsInfo, title: summary.questions == 1 ? "1 question for you" : "\(summary.questions) questions for you")
                }
                if summary.passing > 0 {
                    StatusPill(tone: .pass, title: "\(summary.passing) passed")
                }
            }
            Text("We checked each item against the federal ADA 2010 Standards and California's CBC Chapter 11B. Where the two set different limits, you need to meet the stricter one, so we mark it as the one that applies.")
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Palette.inkMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var checkedLine: String {
        let rooms = report.roomNames.count == 1 ? "1 room" : "\(report.roomNames.count) rooms"
        return "\(rooms), checked \(report.completedAt.formatted(date: .long, time: .omitted))"
    }
}

/// The number that matters most, inked over in red.
private struct FixCount: View {
    let count: Int

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s + 4) {
            Text("\(count)")
                .font(Theme.Typography.hero)
                .foregroundStyle(Theme.Palette.ink)
                .padding(.horizontal, Theme.Spacing.xs)
                .background(alignment: .bottom) {
                    InkStroke(weight: Theme.Stroke.inkBold, color: count > 0 ? Theme.Palette.problem : Theme.Palette.pass, seed: 17)
                        .frame(height: 18)
                        .offset(y: 2)
                }
            Text(count == 0 ? "things to fix" : (count == 1 ? "thing to fix" : "things to fix"))
                .font(Theme.Typography.title)
                .foregroundStyle(Theme.Palette.ink)
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
    }
}

private struct RoomSectionView: View {
    let section: RoomSection
    let reportID: UUID

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            Text(section.name)
                .font(Theme.Typography.title)
                .foregroundStyle(Theme.Palette.ink)
                .accessibilityAddTraits(.isHeader)
            ForEach(section.objectsWithIssues) { group in
                ObjectCard(group: group, reportID: reportID)
            }
            if !section.passing.isEmpty {
                PassingList(items: section.passing)
            }
        }
    }
}

private struct ObjectCard: View {
    let group: ObjectGroup
    let reportID: UUID

    var body: some View {
        Card(variant: .raised) {
            VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                Text(group.subject.label)
                    .font(Theme.Typography.headline)
                    .foregroundStyle(Theme.Palette.ink)
                ForEach(group.issues) { outcome in
                    IssueRow(outcome: outcome, reportID: reportID)
                }
            }
        }
    }
}

/// A question the owner can answer comes first; then a check only the owner can do, a yes or no
/// question, and finally a measured problem.
private struct IssueRow: View {
    let outcome: RuleOutcome
    let reportID: UUID

    var body: some View {
        if let question = OwnerQuestions.question(for: outcome) {
            AskQuestionView(outcome: outcome, question: question, reportID: reportID)
        } else if outcome.isOwnerQuestion {
            OwnerCheckView(outcome: outcome)
        } else if outcome.isQuestion {
            QuestionView(outcome: outcome)
        } else {
            IssueView(outcome: outcome)
        }
    }
}

private struct IssueView: View {
    let outcome: RuleOutcome

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            FindingText(finding: outcome.governing)
            if let measured = outcome.governing.measured, let bound = RequiredBound.parse(outcome.governing.required) {
                FindingGauge(measured: measured, bound: bound)
            }
            RuleRows(outcome: outcome)
        }
    }
}

private struct QuestionView: View {
    @Environment(AppModel.self) private var model
    let outcome: RuleOutcome

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s) {
                Image(systemName: StatusTone.needsInfo.symbol)
                    .foregroundStyle(Theme.Palette.attention)
                FindingText(finding: outcome.governing)
            }
            HStack(spacing: Theme.Spacing.s) {
                AnswerButton(title: "Yes", isSelected: model.answers[outcome.id] == true) { model.answer(outcome.id, yes: true) }
                AnswerButton(title: "No", isSelected: model.answers[outcome.id] == false) { model.answer(outcome.id, yes: false) }
            }
            Text(Citation.list(for: outcome))
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Palette.inkMuted)
        }
    }
}

/// A question the rules need the owner to settle, with the control its kind of answer needs.
private struct AskQuestionView: View {
    @Environment(AppModel.self) private var model
    let outcome: RuleOutcome
    let question: OwnerQuestion
    let reportID: UUID

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s) {
                Image(systemName: StatusTone.needsInfo.symbol)
                    .foregroundStyle(Theme.Palette.attention)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    if let title = outcome.governing.title {
                        Text(title)
                            .font(Theme.Typography.body.weight(.semibold))
                            .foregroundStyle(Theme.Palette.ink)
                    }
                    Text(question.ask.prompt)
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Palette.ink)
                }
                .fixedSize(horizontal: false, vertical: true)
            }
            AnswerControl(question: question, current: model.answer(to: question, inReport: reportID)) { value in
                Task { await model.answer(question, with: value, inReport: reportID) }
            }
            Text(Citation.list(for: outcome))
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Palette.inkMuted)
        }
    }
}

private struct AnswerControl: View {
    let question: OwnerQuestion
    let current: AnswerValue?
    let onAnswer: (AnswerValue?) -> Void

    var body: some View {
        switch question.ask.valueType {
        case .boolean:
            HStack(spacing: Theme.Spacing.s) {
                choice("Yes", value: .bool(true))
                choice("No", value: .bool(false))
            }
        case .choice:
            VStack(spacing: Theme.Spacing.s) {
                ForEach(question.ask.options, id: \.self) { option in
                    choice(OwnerQuestions.optionTitle(option), value: .text(option))
                }
            }
        case .number, .integer:
            NumberAnswerField(ask: question.ask, current: current, onAnswer: onAnswer)
        case .unsupported:
            EmptyView()
        }
    }

    /// Tapping the chosen answer again clears it.
    private func choice(_ title: String, value: AnswerValue) -> some View {
        AnswerButton(title: title, isSelected: current == value) {
            onAnswer(current == value ? nil : value)
        }
    }
}

private struct NumberAnswerField: View {
    let ask: FindingAsk
    let current: AnswerValue?
    let onAnswer: (AnswerValue?) -> Void
    @State private var text = ""
    @State private var problem: String?

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            InkTextField(label: label, text: $text, kind: .number, prompt: ask.valueType == .integer ? "0" : "0.0")
            if let problem {
                Text(problem)
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Palette.problem)
            }
            SecondaryButton(title: isSaved ? "Answer saved" : "Save answer", systemImage: isSaved ? "checkmark" : nil, action: save)
        }
        .onAppear { text = OwnerQuestions.text(for: current) }
        .onChange(of: current) { _, saved in text = OwnerQuestions.text(for: saved) }
    }

    private var label: String {
        ask.unit.isEmpty ? "Your answer" : "Your answer in \(OwnerQuestions.unitName(ask.unit))"
    }

    private var isSaved: Bool {
        current != nil && OwnerQuestions.numberValue(from: text, valueType: ask.valueType) == current
    }

    /// An empty field clears a saved answer.
    private func save() {
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else {
            problem = nil
            if current != nil { onAnswer(nil) }
            return
        }
        guard let value = OwnerQuestions.numberValue(from: trimmed, valueType: ask.valueType) else {
            problem = "Enter a number, like 5 or 4.5."
            return
        }
        problem = nil
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
        onAnswer(value)
    }
}

/// A finding's rule name above what we found, or the message alone when the rule has no name.
private struct FindingText: View {
    let finding: Finding

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            if let title = finding.title {
                Text(title)
                    .font(Theme.Typography.body.weight(.semibold))
                    .foregroundStyle(Theme.Palette.ink)
            }
            Text(finding.message)
                .font(Theme.Typography.body)
                .foregroundStyle(finding.title == nil ? Theme.Palette.ink : Theme.Palette.inkMuted)
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

/// Something we couldn't settle from the scan, such as an object we couldn't identify. It is
/// not a code violation, so it shows no rule and no pass or fail, only a check to tick off.
private struct OwnerCheckView: View {
    @Environment(AppModel.self) private var model
    let outcome: RuleOutcome

    var body: some View {
        let isChecked = model.answers[outcome.id] == true
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s) {
                Image(systemName: StatusTone.needsInfo.symbol)
                    .foregroundStyle(Theme.Palette.attention)
                    .accessibilityHidden(true)
                FindingText(finding: outcome.governing)
            }
            AnswerButton(title: isChecked ? "Checked" : "Mark as checked", isSelected: isChecked) {
                model.answer(outcome.id, yes: !isChecked)
            }
            Text("This isn't a code rule. We couldn't settle it from the scan, so it needs a look from you.")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Palette.inkMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct AnswerButton: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.xs) {
                if isSelected { Image(systemName: "checkmark") }
                Text(title)
            }
            .font(Theme.Typography.label)
            .foregroundStyle(isSelected ? Theme.Palette.sheet : Theme.Palette.ink)
            .frame(maxWidth: .infinity, minHeight: Theme.Size.compactControl)
            .background(RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous).fill(isSelected ? Theme.Palette.ink : Theme.Palette.paper))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}

/// Federal and California side by side, with the one that governs marked.
private struct RuleRows: View {
    let outcome: RuleOutcome

    var body: some View {
        VStack(spacing: Theme.Spacing.xs) {
            ForEach([outcome.federal, outcome.california].compactMap { $0 }, id: \.ruleID) { finding in
                RuleRow(finding: finding, applies: outcome.hasBothJurisdictions && outcome.governs(finding))
            }
        }
    }
}

private struct RuleRow: View {
    let finding: Finding
    let applies: Bool

    var body: some View {
        let tone = StatusTone(finding.status)
        HStack(alignment: .center, spacing: Theme.Spacing.s + 4) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: Theme.Spacing.s) {
                    Text(Citation.jurisdictionName(finding.jurisdiction))
                        .font(Theme.Typography.callout.weight(.bold))
                        .foregroundStyle(Theme.Palette.ink)
                    if applies {
                        Label("Applies", systemImage: "checkmark")
                            .font(Theme.Typography.caption.weight(.bold))
                            .foregroundStyle(Theme.Palette.accent)
                    }
                }
                Text(Citation.text(for: finding))
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Palette.inkMuted)
            }
            Spacer(minLength: Theme.Spacing.s)
            MeasurementText(text: finding.required, color: Theme.Palette.ink)
            Image(systemName: tone.symbol)
                .foregroundStyle(tone.color)
                .accessibilityLabel(finding.status == .pass ? "Passes" : "Does not pass")
        }
        .padding(.horizontal, Theme.Spacing.s + 4)
        .padding(.vertical, Theme.Spacing.s)
        .background(RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous).fill(applies ? Theme.Palette.accentWash : Theme.Palette.paper))
        .accessibilityElement(children: .combine)
    }
}

private struct PassingList: View {
    let items: [(subject: ReportSubject, outcome: RuleOutcome)]
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            Button { withAnimation(Theme.Motion.settle) { isExpanded.toggle() } } label: {
                HStack(spacing: Theme.Spacing.s) {
                    Image(systemName: StatusTone.pass.symbol).foregroundStyle(Theme.Palette.pass)
                    Text(items.count == 1 ? "1 check passed" : "\(items.count) checks passed")
                        .font(Theme.Typography.callout.weight(.bold))
                        .foregroundStyle(Theme.Palette.ink)
                    Spacer()
                    Text(isExpanded ? "Hide" : "Show")
                        .font(Theme.Typography.callout)
                        .foregroundStyle(Theme.Palette.accent)
                }
                .frame(minHeight: Theme.Size.compactControl)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            if isExpanded {
                ForEach(items, id: \.outcome.id) { item in
                    HStack(alignment: .firstTextBaseline) {
                        Text(item.subject.label)
                            .font(Theme.Typography.callout)
                            .foregroundStyle(Theme.Palette.ink)
                        Spacer()
                        if let measured = item.outcome.governing.measured {
                            MeasurementText(text: MeasurementFormat.string(measured), size: .small, color: Theme.Palette.inkMuted)
                        }
                        Text(Citation.text(for: item.outcome.governing))
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Palette.inkMuted)
                    }
                }
            }
        }
    }
}
