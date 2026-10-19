import SwiftUI

struct ScanningHUD: View {
    @Environment(AppModel.self) private var model
    @Environment(\.trayStartsExpanded) private var trayStartsExpanded
    let room: Int
    let onLeave: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s + 4) {
            CaptureTopBar(room: room, onLeave: onLeave)
            if let guidance = model.capture.guidance {
                HUDCapsule {
                    Label(guidance, systemImage: "figure.walk")
                }
                .transition(.opacity)
                .id(guidance)
            }
            Spacer()
            FindingsTray(findings: model.capture.provisionalFindings, startsExpanded: trayStartsExpanded)
            HStack(spacing: Theme.Spacing.s + 4) {
                SecondaryButton(title: "Pause", systemImage: "pause.fill") { model.capture.pause() }
                    .frame(maxWidth: 140)
                PrimaryButton(title: "Finish room", systemImage: "checkmark") {
                    Task { await model.finishRoom() }
                }
            }
            .environment(\.controlSurface, .camera)
        }
        .padding(.horizontal, Theme.Spacing.m)
        .padding(.bottom, Theme.Spacing.s)
        .animation(Theme.Motion.settle, value: model.capture.guidance)
    }
}

/// What the scan has found so far. Collapsed it shows only counts; tap to read the list.
struct FindingsTray: View {
    let findings: [Finding]
    @State private var isExpanded: Bool

    init(findings: [Finding], startsExpanded: Bool = false) {
        self.findings = findings
        _isExpanded = State(initialValue: startsExpanded)
    }

    private var outcomes: [RuleOutcome] {
        RuleComparison.outcomes(from: findings)
            .filter { $0.status != .notApplicable }
            .sorted { $0.status.severity > $1.status.severity }
    }

    var body: some View {
        HUDPanel(padding: Theme.Spacing.s + 4) {
            VStack(alignment: .leading, spacing: Theme.Spacing.s + 4) {
                Button { withAnimation(Theme.Motion.settle) { isExpanded.toggle() } } label: { summary }
                    .buttonStyle(.plain)
                    .accessibilityLabel(isExpanded ? "Hide what we've found" : "Show what we've found")
                if isExpanded { list }
            }
        }
    }

    private var summary: some View {
        HStack(spacing: Theme.Spacing.s) {
            if outcomes.isEmpty {
                Text("Checks show up when you finish this room")
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Palette.sheet.opacity(0.75))
            }
            ForEach(counts, id: \.title) { count in
                StatusPill(tone: count.tone, title: count.title)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.up")
                .font(Theme.Typography.caption.weight(.bold))
                .rotationEffect(.degrees(isExpanded ? 180 : 0))
                .opacity(outcomes.isEmpty ? 0 : 1)
        }
        .frame(minHeight: Theme.Size.compactControl - 12)
        .contentShape(Rectangle())
    }

    private var counts: [(tone: StatusTone, title: String)] {
        let fails = outcomes.filter { $0.status == .fail }.count
        let questions = outcomes.filter { $0.status == .needsInfo }.count
        let passes = outcomes.filter { $0.status == .pass }.count
        return [
            (StatusTone.fail, "\(fails) to fix", fails),
            (StatusTone.needsInfo, "\(questions) to answer", questions),
            (StatusTone.pass, "\(passes) passing", passes),
        ]
        .filter { $0.2 > 0 }
        .map { ($0.0, $0.1) }
    }

    private var list: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.s + 4) {
                    ForEach(outcomes) { outcome in TrayRow(outcome: outcome) }
                }
            }
            .frame(maxHeight: 220)
            Text("These are early results from this walk. The full check runs when you finish.")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Palette.sheet.opacity(0.7))
        }
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }
}

private struct TrayRow: View {
    let outcome: RuleOutcome

    var body: some View {
        let tone = StatusTone(outcome.status)
        HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s) {
            Image(systemName: tone.symbol)
                .foregroundStyle(tone.color, Theme.Palette.sheet)
                .symbolRenderingMode(.palette)
            Text(outcome.governing.message)
                .font(Theme.Typography.callout)
                .lineLimit(3)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let measured = outcome.governing.measured {
                MeasurementText(text: MeasurementFormat.string(measured), size: .small, color: Theme.Palette.sheet)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

extension EnvironmentValues {
    @Entry var trayStartsExpanded = false
}
