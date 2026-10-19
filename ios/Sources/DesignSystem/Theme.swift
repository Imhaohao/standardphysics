import SwiftUI

/// The paper-and-ink palette and type shared with the web workspace. Every color and font in
/// the app comes from here.
enum Theme {
    enum Palette {
        static let paper = Color(hex: 0xF6F5F1)
        static let sheet = Color(hex: 0xFCFBF8)
        static let rule = Color(hex: 0xE3E0D8)
        static let ink = Color(hex: 0x1B1C1E)
        static let inkMuted = Color(hex: 0x5D5E61)
        static let inkFaint = Color(hex: 0x8A8A88)
        static let accent = Color(hex: 0x2F5E9E)
        static let problem = Color(hex: 0xC8372D)
        static let pass = Color(hex: 0x2E7D4F)
        static let attention = Color(hex: 0x9A6200)
        static let gridMinor = Color(hex: 0xECEBE5)
        static let gridMajor = Color(hex: 0xE0DED6)
    }

    enum Typography {
        static let displayFamily = "Libre Franklin"
        static let bodyFamily = "Karla"
        static let figureFamily = "Atkinson Hyperlegible Mono"

        static let display = Font.custom(displayFamily, size: 34, relativeTo: .largeTitle).weight(.heavy)
        static let title = Font.custom(displayFamily, size: 22, relativeTo: .title2).weight(.bold)
        static let headline = Font.custom(bodyFamily, size: 17, relativeTo: .headline).weight(.bold)
        static let body = Font.custom(bodyFamily, size: 17, relativeTo: .body)
        static let callout = Font.custom(bodyFamily, size: 15, relativeTo: .callout).weight(.medium)
        static let caption = Font.custom(bodyFamily, size: 13, relativeTo: .caption)
        static let measurement = Font.custom(figureFamily, size: 15, relativeTo: .callout).weight(.medium)
        static let measurementLarge = Font.custom(figureFamily, size: 22, relativeTo: .title3).weight(.bold)
    }

    enum Spacing {
        static let xs: CGFloat = 4
        static let s: CGFloat = 8
        static let m: CGFloat = 16
        static let l: CGFloat = 24
        static let xl: CGFloat = 40
    }

    enum Radius {
        static let control: CGFloat = 12
        static let card: CGFloat = 20
    }

    enum Motion {
        static let settle = Animation.timingCurve(0.22, 1, 0.36, 1, duration: 0.45)
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}

extension UIColor {
    convenience init(hex: UInt32) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: 1
        )
    }
}
