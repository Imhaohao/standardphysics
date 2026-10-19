import SwiftUI

struct ProcessingView: View {
    @Environment(AppModel.self) private var model
    private let expectedSeconds: TimeInterval = 60

    var body: some View {
        ZStack {
            PaperBackground()
            if let state = model.processing {
                content(state)
                    .padding(Theme.Spacing.l)
                    .frame(maxWidth: Theme.Size.readable)
            }
        }
    }

    private func content(_ state: ProcessingState) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xl) {
            Spacer()
            VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                Text(state.failure == nil ? "Checking your space" : "We hit a snag")
                    .font(Theme.Typography.display)
                    .foregroundStyle(Theme.Palette.ink)
                    .accessibilityAddTraits(.isHeader)
                InkProgress(fraction: state.failure == nil ? state.fraction : 0)
                    .frame(height: 22)
            }
            StageList(current: state.stage, isFinished: state.fraction >= 1, hasFailed: state.failure != nil)
            Spacer()
            footer(state)
        }
    }

    @ViewBuilder private func footer(_ state: ProcessingState) -> some View {
        if let failure = state.failure {
            VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                Text(failure)
                    .font(Theme.Typography.body)
                    .foregroundStyle(Theme.Palette.ink)
                    .fixedSize(horizontal: false, vertical: true)
                PrimaryButton(title: "Try again", systemImage: "arrow.clockwise") { Task { await model.retryProcessing() } }
                SecondaryButton(title: "Back to your scans") { model.goHome() }
            }
        } else {
            TimelineView(.periodic(from: state.startedAt, by: 1)) { context in
                ElapsedNote(elapsed: context.date.timeIntervalSince(state.startedAt), expected: expectedSeconds)
            }
        }
    }
}

/// The brush pulled across the page as far as the work has got.
private struct InkProgress: View {
    let fraction: Double
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack(alignment: .leading) {
            Rectangle()
                .fill(Theme.Palette.gridMajor)
                .frame(height: Theme.Stroke.hairline)
            InkStrokeCanvas(path: .horizontal, progress: fraction, style: InkBrushStyle(weight: Theme.Stroke.inkWeight * 1.4, seed: 31), color: Theme.Palette.ink)
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.8), value: fraction)
        .accessibilityElement()
        .accessibilityLabel("Progress")
        .accessibilityValue("\(Int(fraction * 100)) percent")
    }
}

private struct StageList: View {
    let current: ProcessingStage
    let isFinished: Bool
    let hasFailed: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            ForEach(ProcessingStage.allCases, id: \.self) { stage in
                HStack(spacing: Theme.Spacing.s + 4) {
                    marker(for: stage)
                        .frame(width: 22, height: 22)
                    Text(stage.title)
                        .font(stage == current ? Theme.Typography.headline : Theme.Typography.body)
                        .foregroundStyle(stage > current ? Theme.Palette.inkFaint : Theme.Palette.ink)
                }
                .accessibilityElement(children: .combine)
            }
        }
    }

    @ViewBuilder private func marker(for stage: ProcessingStage) -> some View {
        if stage < current || (stage == current && isFinished) {
            Image(systemName: "checkmark.circle.fill").foregroundStyle(Theme.Palette.pass)
        } else if stage == current && hasFailed {
            Image(systemName: "exclamationmark.circle.fill").foregroundStyle(Theme.Palette.problem)
        } else if stage == current {
            ProgressView().tint(Theme.Palette.ink)
        } else {
            Circle().stroke(Theme.Palette.inkFaint, lineWidth: 1.5).padding(3)
        }
    }
}

private struct ElapsedNote: View {
    let elapsed: TimeInterval
    let expected: TimeInterval

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.m) {
            MeasurementText(text: Duration.seconds(Int(elapsed)).formatted(.time(pattern: .minuteSecond)), size: .large)
            Text(elapsed < expected
                ? "This takes up to a minute. Keep the app open until it's done."
                : "This is taking longer than usual. Your rooms are saved on this phone, so nothing is lost if you have to leave.")
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Palette.inkMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
