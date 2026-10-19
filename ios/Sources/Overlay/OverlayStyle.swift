import SwiftUI
import UIKit

/// Overlay roles mapped onto the shared palette and type. Views and entities reference these, never raw colors.
enum OverlayStyle {
    struct Tint {
        let color: UIColor
        let opacity: Float
    }

    enum Scene {
        static let edgeThickness: Float = 0.008
        static let planeThickness: Float = 0.002

        static let wallFill = Tint(color: UIColor(Theme.Palette.sheet), opacity: 0.28)
        static let wallEdge = Tint(color: UIColor(Theme.Palette.ink), opacity: 0.9)
        static let openingFill = Tint(color: UIColor(Theme.Palette.accent), opacity: 0.32)
        static let openingEdge = Tint(color: UIColor(Theme.Palette.accent), opacity: 1)
        static let windowFill = Tint(color: UIColor(Theme.Palette.sheet), opacity: 0.1)
        static let windowEdge = Tint(color: UIColor(Theme.Palette.inkFaint), opacity: 0.5)
        static let objectEdge = Tint(color: UIColor(Theme.Palette.ink), opacity: 0.95)
        static let detectedEdge = Tint(color: UIColor(Theme.Palette.ink), opacity: 0.75)
    }

    enum Label {
        static let primaryFont = Theme.Typography.measurement
        static let secondaryFont = Font.custom(Theme.Typography.figureFamily, size: 12, relativeTo: .caption2)
        static let primaryText = Theme.Palette.ink
        static let secondaryText = Theme.Palette.inkMuted
        static let fill = Theme.Palette.sheet.opacity(0.94)
        static let leader = Theme.Palette.ink.opacity(0.7)
        static let dimensionLine = Theme.Palette.accent
        static let shadow = Theme.Palette.ink.opacity(0.18)
        static let shadowRadius: CGFloat = 6
        static let shadowOffset: CGFloat = 2
        static let cornerRadius = Theme.Radius.control
        static let horizontalPadding = Theme.Spacing.s + Theme.Spacing.xs
        static let verticalPadding = Theme.Spacing.xs + 2
        static let anchorDotSize: CGFloat = 6
        static let leaderWidth: CGFloat = 1
        static let dimensionLineWidth: CGFloat = 2
        /// Generous per-character advance of the figure face at the label sizes, used before layout.
        static let primaryAdvance: CGFloat = 9.5
        static let secondaryAdvance: CGFloat = 7.6
        static let iconWidth: CGFloat = 16
        static let height: CGFloat = 32
    }

    static func meshTint(for surface: MeshSurface) -> Tint? {
        switch surface {
        case .none: Tint(color: UIColor(Theme.Palette.rule), opacity: 0.1)
        case .wall: Tint(color: UIColor(Theme.Palette.sheet), opacity: 0.14)
        case .floor: Tint(color: UIColor(Theme.Palette.gridMajor), opacity: 0.22)
        case .ceiling: nil
        case .table: Tint(color: UIColor(Theme.Palette.ink), opacity: 0.2)
        case .seat: Tint(color: UIColor(Theme.Palette.inkMuted), opacity: 0.24)
        case .window: Tint(color: UIColor(Theme.Palette.inkFaint), opacity: 0.12)
        case .door: Tint(color: UIColor(Theme.Palette.accent), opacity: 0.26)
        }
    }

    static func color(for status: FindingStatus) -> Color? {
        switch status {
        case .pass: Theme.Palette.pass
        case .fail: Theme.Palette.problem
        case .needsInfo: Theme.Palette.attention
        case .notApplicable: nil
        }
    }

    static func symbol(for status: FindingStatus) -> String? {
        switch status {
        case .pass: "checkmark.circle.fill"
        case .fail: "xmark.octagon.fill"
        case .needsInfo: "questionmark.circle.fill"
        case .notApplicable: nil
        }
    }

    static func symbol(for kind: MeasurementKind) -> String {
        switch kind {
        case .topHeight: "arrow.up.and.down"
        case .clearWidth, .passageWidth: "arrow.left.and.right"
        }
    }
}
