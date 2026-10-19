import SwiftUI

/// Measurement chips, finding badges, their leaders and dimension lines, in screen space.
struct LiveLabelOverlay: View {
    let labels: [PlacedOverlayLabel]

    var body: some View {
        ZStack(alignment: .topLeading) {
            Canvas { context, _ in
                labels.forEach { LabelGuides.draw($0, in: &context) }
            }
            ForEach(labels) { placed in
                OverlayChip(content: placed.label.content)
                    .position(x: placed.frame.midX, y: placed.frame.midY)
            }
        }
        .allowsHitTesting(false)
    }
}

private enum LabelGuides {
    static let dimensionTickLength: CGFloat = 10

    static func draw(_ placed: PlacedOverlayLabel, in context: inout GraphicsContext) {
        drawDimensionLine(placed.span, in: &context)
        drawLeader(from: placed.anchor, to: placed.frame, in: &context)
        drawAnchorDot(at: placed.anchor, in: &context)
    }

    private static func drawDimensionLine(_ span: [CGPoint], in context: inout GraphicsContext) {
        guard span.count == 2 else { return }
        let style = StrokeStyle(lineWidth: OverlayStyle.Label.dimensionLineWidth, lineCap: .round)
        var line = Path()
        line.move(to: span[0])
        line.addLine(to: span[1])
        span.forEach { line.addPath(tick(at: $0, across: span)) }
        context.stroke(line, with: .color(OverlayStyle.Label.dimensionLine), style: style)
    }

    private static func tick(at point: CGPoint, across span: [CGPoint]) -> Path {
        let dx = span[1].x - span[0].x
        let dy = span[1].y - span[0].y
        let length = max(hypot(dx, dy), 1)
        let normal = CGPoint(x: -dy / length * dimensionTickLength / 2, y: dx / length * dimensionTickLength / 2)
        var path = Path()
        path.move(to: CGPoint(x: point.x - normal.x, y: point.y - normal.y))
        path.addLine(to: CGPoint(x: point.x + normal.x, y: point.y + normal.y))
        return path
    }

    private static func drawLeader(from anchor: CGPoint, to frame: CGRect, in context: inout GraphicsContext) {
        let target = CGPoint(x: min(max(anchor.x, frame.minX), frame.maxX), y: min(max(anchor.y, frame.minY), frame.maxY))
        var leader = Path()
        leader.move(to: anchor)
        leader.addLine(to: target)
        context.stroke(leader, with: .color(OverlayStyle.Label.leader), lineWidth: OverlayStyle.Label.leaderWidth)
    }

    private static func drawAnchorDot(at point: CGPoint, in context: inout GraphicsContext) {
        let size = OverlayStyle.Label.anchorDotSize
        let dot = Path(ellipseIn: CGRect(x: point.x - size / 2, y: point.y - size / 2, width: size, height: size))
        context.fill(dot, with: .color(OverlayStyle.Label.primaryText))
    }
}

struct OverlayChip: View {
    let content: OverlayLabelContent

    var body: some View {
        HStack(spacing: LabelProjector.contentSpacing) {
            statusIcon
            contentText
        }
        .padding(.horizontal, OverlayStyle.Label.horizontalPadding)
        .padding(.vertical, OverlayStyle.Label.verticalPadding)
        .background(OverlayStyle.Label.fill, in: RoundedRectangle(cornerRadius: OverlayStyle.Label.cornerRadius, style: .continuous))
        .shadow(color: OverlayStyle.Label.shadow, radius: OverlayStyle.Label.shadowRadius, y: OverlayStyle.Label.shadowOffset)
        .fixedSize()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(OverlayChipDescription.text(for: content))
    }

    @ViewBuilder private var statusIcon: some View {
        if let status = content.status, let symbol = OverlayStyle.symbol(for: status), let color = OverlayStyle.color(for: status) {
            Image(systemName: symbol)
                .font(OverlayStyle.Label.primaryFont)
                .foregroundStyle(color)
        }
    }

    @ViewBuilder private var contentText: some View {
        switch content {
        case .measurement(let kind, let length, _):
            Image(systemName: OverlayStyle.symbol(for: kind))
                .font(OverlayStyle.Label.secondaryFont)
                .foregroundStyle(OverlayStyle.Label.secondaryText)
            Text(length.inches)
                .font(OverlayStyle.Label.primaryFont)
                .foregroundStyle(OverlayStyle.Label.primaryText)
            Text(length.centimeters)
                .font(OverlayStyle.Label.secondaryFont)
                .foregroundStyle(OverlayStyle.Label.secondaryText)
        case .finding(let section, _):
            Text(section)
                .font(OverlayStyle.Label.primaryFont)
                .foregroundStyle(OverlayStyle.Label.primaryText)
        }
    }
}

nonisolated enum OverlayChipDescription {
    static func text(for content: OverlayLabelContent) -> String {
        let status = content.status.flatMap(statusText(_:)).map { ", \($0)" } ?? ""
        switch content {
        case .measurement(let kind, let length, _):
            return "\(kindText(kind)) \(length.inches), \(length.centimeters)\(status)"
        case .finding(let section, _):
            return "Section \(section)\(status)"
        }
    }

    private static func kindText(_ kind: MeasurementKind) -> String {
        switch kind {
        case .topHeight: "Top height"
        case .clearWidth: "Clear width"
        case .passageWidth: "Narrowest passage"
        }
    }

    private static func statusText(_ status: FindingStatus) -> String? {
        switch status {
        case .pass: "looks compliant"
        case .fail: "likely a problem"
        case .needsInfo: "needs more information"
        case .notApplicable: nil
        }
    }
}
