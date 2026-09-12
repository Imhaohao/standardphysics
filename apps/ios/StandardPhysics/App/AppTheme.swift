import SwiftUI

enum AppTheme {
    static let canvas = Color(red: 0.95, green: 0.94, blue: 0.90)
    static let panel = Color(red: 1.0, green: 0.99, blue: 0.96)
    static let ink = Color(red: 0.08, green: 0.09, blue: 0.08)
    static let mutedInk = Color(red: 0.34, green: 0.35, blue: 0.32)
    static let accent = Color(red: 0.10, green: 0.42, blue: 0.34)
    static let scanLine = Color(red: 0.65, green: 0.88, blue: 0.66)
    static let warning = Color(red: 0.74, green: 0.34, blue: 0.18)
    static let onDark = Color.white
    static let transparent = Color.clear
    static let captureScrimTop = Color.black.opacity(0.56)
    static let captureScrimBottom = Color.black.opacity(0.50)
    static let captureChrome = Color.black.opacity(0.58)
    static let captureProgress = Color.black.opacity(0.72)
    static let captureMap = Color.black.opacity(0.62)
    static let coveragePendingBright = Color.white.opacity(0.90)
    static let coveragePendingDim = Color.white.opacity(0.40)
    static let secondaryPressed = Color.black.opacity(0.08)
    static let secondaryIdle = Color.black.opacity(0.04)
    static let fieldOutline = Color.black.opacity(0.14)

    enum Typography {
        static let hero = Font.system(size: 50, weight: .bold, design: .rounded)
        static let status = Font.system(size: 38, weight: .bold, design: .rounded)
        static let guidanceSymbol = Font.system(size: 34, weight: .bold)
        static let statusSymbol = Font.system(size: 38, weight: .bold)
    }

    enum Spacing {
        static let page: CGFloat = 28
        static let section: CGFloat = 24
        static let card: CGFloat = 18
        static let control: CGFloat = 16
        static let compact: CGFloat = 14
        static let small: CGFloat = 12
    }

    enum Radius {
        static let control: CGFloat = 18
        static let field: CGFloat = 14
        static let map: CGFloat = 22
    }

    enum Size {
        static let touchTarget: CGFloat = 44
        static let guidanceMark: CGFloat = 68
        static let statusMark: CGFloat = 82
        static let coverageMapHeight: CGFloat = 136
    }

    enum Shadow {
        static let color = Color.black.opacity(0.12)
        static let radius: CGFloat = 12
        static let y: CGFloat = 5
    }

    enum Motion {
        static let quick = Animation.easeOut(duration: 0.25)
        static let pulse = Animation.easeInOut(duration: 1).repeatForever(autoreverses: true)
    }
}

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .frame(maxWidth: .infinity)
            .padding(.vertical, AppTheme.Spacing.control)
            .foregroundStyle(AppTheme.onDark)
            .background(configuration.isPressed ? AppTheme.ink.opacity(0.78) : AppTheme.ink)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .frame(maxWidth: .infinity)
            .padding(.vertical, AppTheme.Spacing.compact)
            .foregroundStyle(AppTheme.ink)
            .background(configuration.isPressed ? AppTheme.secondaryPressed : AppTheme.secondaryIdle)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.field, style: .continuous))
    }
}

struct EarlyDoneButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .frame(maxWidth: .infinity)
            .padding(.vertical, AppTheme.Spacing.control)
            .foregroundStyle(AppTheme.onDark)
            .background(configuration.isPressed ? AppTheme.captureProgress : AppTheme.captureChrome)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
    }
}
