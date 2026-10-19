import SwiftUI

enum ButtonVariant {
    case primary
    case secondary
    case quiet
}

/// What a control sits on. Over the camera, primary turns to paper and secondary to glass so
/// both stay legible on a moving picture.
enum ControlSurface {
    case paper
    case camera
}

extension EnvironmentValues {
    @Entry var controlSurface: ControlSurface = .paper
}

struct InkButtonStyle: ButtonStyle {
    let variant: ButtonVariant
    var height: CGFloat = Theme.Size.control

    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.controlSurface) private var controlSurface

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.Typography.label)
            .foregroundStyle(foreground)
            .padding(.horizontal, Theme.Spacing.m)
            .frame(minHeight: height)
            .frame(maxWidth: variant == .quiet ? nil : .infinity)
            .background { surface }
            .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.control))
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .opacity(isEnabled ? (configuration.isPressed ? 0.85 : 1) : 0.4)
            .animation(Theme.Motion.settle, value: configuration.isPressed)
    }

    private var foreground: Color {
        switch (variant, controlSurface) {
        case (.primary, .paper), (.secondary, .camera), (.quiet, .camera): Theme.Palette.sheet
        case (.primary, .camera), (.secondary, .paper): Theme.Palette.ink
        case (.quiet, .paper): Theme.Palette.accent
        }
    }

    @ViewBuilder private var surface: some View {
        let shape = RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous)
        switch (variant, controlSurface) {
        case (.primary, .paper):
            shape.fill(Theme.Palette.ink)
        case (.primary, .camera):
            shape.fill(Theme.Palette.sheet)
        case (.secondary, .paper):
            shape.fill(Theme.Palette.sheet)
                .shadow(color: Theme.Elevation.cardColor, radius: 6, y: 2)
                .overlay(shape.stroke(Theme.Elevation.ringColor, lineWidth: Theme.Stroke.hairline))
        case (.secondary, .camera):
            Color.clear.glassEffect(.regular.tint(Theme.Palette.camera.opacity(0.3)).interactive(), in: shape)
        case (.quiet, _):
            Color.clear
        }
    }
}

struct PrimaryButton: View {
    let title: String
    var systemImage: String?
    let action: () -> Void

    var body: some View {
        Button(action: action) { ButtonLabel(title: title, systemImage: systemImage) }
            .buttonStyle(InkButtonStyle(variant: .primary))
    }
}

struct SecondaryButton: View {
    let title: String
    var systemImage: String?
    let action: () -> Void

    var body: some View {
        Button(action: action) { ButtonLabel(title: title, systemImage: systemImage) }
            .buttonStyle(InkButtonStyle(variant: .secondary))
    }
}

struct ButtonLabel: View {
    let title: String
    var systemImage: String?

    var body: some View {
        HStack(spacing: Theme.Spacing.s) {
            if let systemImage {
                Image(systemName: systemImage).imageScale(.medium)
            }
            Text(title)
        }
    }
}

#Preview {
    VStack(spacing: Theme.Spacing.m) {
        PrimaryButton(title: "Start a new scan", systemImage: "viewfinder") {}
        SecondaryButton(title: "Finish and check") {}
        PrimaryButton(title: "Disabled") {}.disabled(true)
    }
    .padding()
    .background(PaperBackground())
}
