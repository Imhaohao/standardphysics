import CoreGraphics
import simd

/// Projects world-anchored labels to the screen and lays them out without overlaps.
enum LabelProjector {
    static let contentSpacing = Theme.Spacing.xs + 2

    static func place(
        _ labels: [OverlayLabel],
        in bounds: CGRect,
        scale: CGFloat,
        project: (SIMD3<Float>) -> CGPoint?
    ) -> [PlacedOverlayLabel] {
        let projected = labels.compactMap { label in project(label.anchor).map { (label, $0) } }
        let requests = projected.map { label, point in
            LabelPlacementRequest(id: label.id, anchor: point, size: estimatedSize(of: label.content, scale: scale), priority: label.priority)
        }
        let labelsByID = Dictionary(projected.map { ($0.0.id, $0.0) }) { first, _ in first }
        return LabelLayout.place(requests, in: bounds).compactMap { placement in
            guard let label = labelsByID[placement.id] else { return nil }
            let span = label.span.compactMap(project)
            return PlacedOverlayLabel(
                label: label,
                anchor: placement.anchor,
                frame: placement.frame,
                span: span.count == label.span.count ? span : []
            )
        }
    }

    static func estimatedSize(of content: OverlayLabelContent, scale: CGFloat) -> CGSize {
        let style = OverlayStyle.Label.self
        let statusWidth = content.status.flatMap(OverlayStyle.symbol(for:)) == nil ? 0 : style.iconWidth + contentSpacing
        let textWidth: CGFloat = switch content {
        case .measurement(_, let length, _):
            style.iconWidth + contentSpacing
                + CGFloat(length.inches.count) * style.primaryAdvance + contentSpacing
                + CGFloat(length.centimeters.count) * style.secondaryAdvance
        case .finding(let section, _):
            CGFloat(section.count) * style.primaryAdvance
        }
        let width = (statusWidth + textWidth) * scale + style.horizontalPadding * 2
        return CGSize(width: width.rounded(.up), height: (style.height * scale).rounded(.up))
    }
}
