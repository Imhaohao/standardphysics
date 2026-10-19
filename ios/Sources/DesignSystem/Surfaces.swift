import SwiftUI

enum CardVariant {
    case sheet
    case raised
    case flat
}

struct Card<Content: View>: View {
    var variant: CardVariant = .sheet
    var padding: CGFloat = Theme.Spacing.m
    @ViewBuilder let content: Content

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous)
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background {
                shape.fill(fill)
                    .shadow(color: shadowColor, radius: Theme.Elevation.cardRadius, y: Theme.Elevation.cardY)
                    .overlay(shape.stroke(Theme.Elevation.ringColor, lineWidth: Theme.Stroke.hairline))
            }
    }

    private var fill: Color {
        variant == .flat ? Theme.Palette.paper : Theme.Palette.sheet
    }

    private var shadowColor: Color {
        switch variant {
        case .sheet: Theme.Elevation.cardColor.opacity(0.6)
        case .raised: Theme.Elevation.cardColor
        case .flat: .clear
        }
    }
}

enum StatusTone {
    case pass
    case fail
    case needsInfo
    case neutral

    init(_ status: FindingStatus) {
        switch status {
        case .pass: self = .pass
        case .fail: self = .fail
        case .needsInfo: self = .needsInfo
        case .notApplicable: self = .neutral
        }
    }

    var color: Color {
        switch self {
        case .pass: Theme.Palette.pass
        case .fail: Theme.Palette.problem
        case .needsInfo: Theme.Palette.attention
        case .neutral: Theme.Palette.inkMuted
        }
    }

    var wash: Color {
        switch self {
        case .pass: Theme.Palette.passWash
        case .fail: Theme.Palette.problemWash
        case .needsInfo: Theme.Palette.attentionWash
        case .neutral: Theme.Palette.rule
        }
    }

    var symbol: String {
        switch self {
        case .pass: "checkmark.circle.fill"
        case .fail: "xmark.circle.fill"
        case .needsInfo: "questionmark.circle.fill"
        case .neutral: "minus.circle.fill"
        }
    }
}

struct StatusPill: View {
    let tone: StatusTone
    let title: String

    var body: some View {
        HStack(spacing: Theme.Spacing.xs) {
            Image(systemName: tone.symbol).imageScale(.small)
            Text(title).lineLimit(1)
        }
        .fixedSize()
        .font(Theme.Typography.caption.weight(.bold))
        .foregroundStyle(tone.color)
        .padding(.horizontal, Theme.Spacing.s + 2)
        .padding(.vertical, Theme.Spacing.xs + 1)
        .background(Capsule().fill(tone.wash))
    }
}

/// A measured figure with its unit, in the figure face so columns of numbers line up.
struct MeasurementText: View {
    enum Size {
        case small
        case regular
        case large
    }

    let text: String
    var size: Size = .regular
    var color: Color = Theme.Palette.ink

    var body: some View {
        Text(text)
            .font(font)
            .monospacedDigit()
            .foregroundStyle(color)
    }

    private var font: Font {
        switch size {
        case .small: Theme.Typography.measurementSmall
        case .regular: Theme.Typography.measurement
        case .large: Theme.Typography.measurementLarge
        }
    }
}

#Preview {
    VStack(spacing: Theme.Spacing.m) {
        Card {
            HStack {
                StatusPill(tone: .fail, title: "Fix this")
                StatusPill(tone: .pass, title: "Passes")
                StatusPill(tone: .needsInfo, title: "Needs your answer")
            }
        }
        MeasurementText(text: "35.5 in", size: .large)
    }
    .padding()
    .background(PaperBackground())
}
