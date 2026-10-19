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
                        ForEach(ReportGrouping.sections(for: report)) { section in
                            RoomSectionView(section: section)
                        }
                    }
                    .padding(Theme.Spacing.m)
                    .padding(.bottom, Theme.Spacing.xl)
                    .frame(maxWidth: Theme.Size.readable, alignment: .leading)
                }
            }
        }
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

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            Text(section.name)
                .font(Theme.Typography.title)
                .foregroundStyle(Theme.Palette.ink)
                .accessibilityAddTraits(.isHeader)
            ForEach(section.objectsWithIssues) { group in
                ObjectCard(group: group)
            }
            if !section.passing.isEmpty {
                PassingList(items: section.passing)
            }
        }
    }
}

private struct ObjectCard: View {
    let group: ObjectGroup

    var body: some View {
        Card(variant: .raised) {
            VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                Text(group.subject.label)
                    .font(Theme.Typography.headline)
                    .foregroundStyle(Theme.Palette.ink)
                ForEach(group.issues) { outcome in
                    if outcome.status == .needsInfo {
                        QuestionView(outcome: outcome)
                    } else {
                        IssueView(outcome: outcome)
                    }
                }
            }
        }
    }
}

private struct IssueView: View {
    let outcome: RuleOutcome

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            Text(outcome.governing.message)
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
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
                Text(outcome.governing.message)
                    .font(Theme.Typography.body.weight(.semibold))
                    .foregroundStyle(Theme.Palette.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: Theme.Spacing.s) {
                AnswerButton(title: "Yes", isSelected: model.answers[outcome.id] == true) { model.answer(outcome.id, yes: true) }
                AnswerButton(title: "No", isSelected: model.answers[outcome.id] == false) { model.answer(outcome.id, yes: false) }
            }
            Text(citations)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Palette.inkMuted)
        }
    }

    private var citations: String {
        [outcome.federal, outcome.california].compactMap { $0 }.map(Citation.text(for:)).joined(separator: " and ")
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
