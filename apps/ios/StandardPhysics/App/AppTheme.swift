import SwiftUI

enum AppTheme {
    static let canvas = Color(red: 0.95, green: 0.94, blue: 0.90)
    static let panel = Color(red: 1.0, green: 0.99, blue: 0.96)
    static let ink = Color(red: 0.08, green: 0.09, blue: 0.08)
    static let mutedInk = Color(red: 0.34, green: 0.35, blue: 0.32)
    static let accent = Color(red: 0.10, green: 0.42, blue: 0.34)
    static let scanLine = Color(red: 0.65, green: 0.88, blue: 0.66)
    static let warning = Color(red: 0.74, green: 0.34, blue: 0.18)
}

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 17)
            .foregroundStyle(.white)
            .background(configuration.isPressed ? AppTheme.ink.opacity(0.78) : AppTheme.ink)
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 15)
            .foregroundStyle(AppTheme.ink)
            .background(configuration.isPressed ? Color.black.opacity(0.08) : Color.black.opacity(0.04))
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}
