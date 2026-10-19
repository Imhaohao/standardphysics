import SwiftUI

/// A short scale with the allowed range shaded and an ink dimension line spanning the gap
/// between the limit and what we measured.
struct FindingGauge: View {
    let measured: MeasuredValue
    let bound: RequiredBound

    private let height: CGFloat = 66

    var body: some View {
        let value = MeasurementFormat.displayValue(measured)
        let gap = GaugeGeometry(value: value, bound: bound)
        GeometryReader { proxy in
            let width = proxy.size.width
            let x = { (number: Double) in gap.position(of: number, width: width) }
            ZStack(alignment: .topLeading) {
                Rectangle()
                    .fill(Theme.Palette.passWash)
                    .frame(width: max(0, x(gap.allowed.upperBound) - x(gap.allowed.lowerBound)), height: 14)
                    .offset(x: x(gap.allowed.lowerBound), y: 38)
                Rectangle()
                    .fill(Theme.Palette.inkFaint)
                    .frame(width: width, height: Theme.Stroke.hairline)
                    .offset(y: 45)
                ForEach(gap.limits, id: \.self) { limit in
                    Rectangle()
                        .fill(Theme.Palette.ink)
                        .frame(width: 1.5, height: 22)
                        .offset(x: x(limit) - 0.75, y: 34)
                    MeasurementText(text: MeasurementFormat.trimmed(limit), size: .small, color: Theme.Palette.inkMuted)
                        .fixedSize()
                        .position(x: x(limit), y: 63)
                }
                Circle()
                    .fill(Theme.Palette.problem)
                    .frame(width: 10, height: 10)
                    .offset(x: x(value) - 5, y: 40)
                if let nearest = gap.nearestLimit {
                    let span = min(x(nearest), x(value))...max(x(nearest), x(value))
                    InkDimensionLine(span: (span.lowerBound / width)...(span.upperBound / width), color: Theme.Palette.problem)
                        .frame(width: width, height: 18)
                        .offset(y: 12)
                    MeasurementText(text: gap.label(unit: MeasurementFormat.displayUnit(measured)), size: .small, color: Theme.Palette.problem)
                        .fixedSize()
                        .position(x: (span.lowerBound + span.upperBound) / 2, y: 6)
                }
            }
        }
        .frame(height: height)
        .padding(.horizontal, Theme.Spacing.s)
        .accessibilityElement()
        .accessibilityLabel(accessibilityText)
    }

    private var accessibilityText: String {
        let gap = GaugeGeometry(value: MeasurementFormat.displayValue(measured), bound: bound)
        return "Measured \(MeasurementFormat.string(measured)), \(gap.label(unit: MeasurementFormat.displayUnit(measured)))"
    }
}

nonisolated struct GaugeGeometry {
    let value: Double
    let bound: RequiredBound

    var limits: [Double] {
        switch bound {
        case .atMost(let limit), .atLeast(let limit): [limit]
        case .between(let low, let high): [low, high]
        }
    }

    var domain: ClosedRange<Double> {
        let numbers = limits + [value]
        let low = numbers.min() ?? 0
        let high = numbers.max() ?? 1
        let pad = max((high - low) * 0.9, 2)
        return (low - pad)...(high + pad)
    }

    var allowed: ClosedRange<Double> {
        switch bound {
        case .atMost(let limit): domain.lowerBound...limit
        case .atLeast(let limit): limit...domain.upperBound
        case .between(let low, let high): low...high
        }
    }

    var nearestLimit: Double? {
        guard !allowed.contains(value) else { return nil }
        return limits.min { abs($0 - value) < abs($1 - value) }
    }

    func position(of number: Double, width: CGFloat) -> CGFloat {
        let share = (number - domain.lowerBound) / (domain.upperBound - domain.lowerBound)
        return CGFloat(share) * width
    }

    func label(unit: String) -> String {
        guard let nearest = nearestLimit else { return "within the limit" }
        let amount = MeasurementFormat.trimmed(abs(value - nearest))
        return value > nearest ? "\(amount) \(unit) over" : "\(amount) \(unit) short"
    }
}
