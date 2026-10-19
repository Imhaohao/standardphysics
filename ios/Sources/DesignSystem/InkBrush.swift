import SwiftUI

/// A polyline in unit space (0...1 on both axes) that the brush follows.
nonisolated struct InkPath: Sendable, Equatable {
    let points: [CGPoint]

    /// A hand-pulled underline: a slow rise with a small hook where the brush lifts.
    static let underline = InkPath(points: [
        CGPoint(x: 0.0, y: 0.62),
        CGPoint(x: 0.18, y: 0.55),
        CGPoint(x: 0.42, y: 0.5),
        CGPoint(x: 0.7, y: 0.44),
        CGPoint(x: 0.9, y: 0.4),
        CGPoint(x: 0.97, y: 0.34),
        CGPoint(x: 1.0, y: 0.22),
    ])

    static let horizontal = InkPath(points: [CGPoint(x: 0, y: 0.5), CGPoint(x: 1, y: 0.5)])
    static let vertical = InkPath(points: [CGPoint(x: 0.5, y: 1), CGPoint(x: 0.5, y: 0)])

    func scaled(to rect: CGRect) -> [CGPoint] {
        points.map { CGPoint(x: rect.minX + $0.x * rect.width, y: rect.minY + $0.y * rect.height) }
    }
}

/// Stroke texture borrowed from the web brush: a soft bleed, a body whose width wanders,
/// stray fibers and a pooled start where the brush first touched the paper.
nonisolated struct InkBrushStyle: Sendable {
    var weight: CGFloat
    var seed: UInt64
    var bleedOpacity: CGFloat = 0.12
    var bodyOpacity: CGFloat = 0.94
    var fiberChance: CGFloat = 0.05
    var pooledStart = true
}

nonisolated enum InkBrush {
    private static let sampleSpacing: CGFloat = 1.5
    private static let taperShare: CGFloat = 0.07

    static func draw(points: [CGPoint], progress: CGFloat, style: InkBrushStyle, color: Color, in context: inout GraphicsContext) {
        let samples = cut(resample(points), at: progress)
        guard samples.count > 1 else { return }
        drawBleed(samples, style: style, color: color, in: &context)
        drawFibers(samples, style: style, color: color, in: &context)
        drawBody(samples, style: style, color: color, in: &context)
        if style.pooledStart { drawPool(at: samples[0], style: style, color: color, in: &context) }
    }

    private static func drawBleed(_ samples: [CGPoint], style: InkBrushStyle, color: Color, in context: inout GraphicsContext) {
        var layer = context
        layer.opacity = style.bleedOpacity
        layer.drawLayer { bleed in
            for index in 1..<samples.count {
                let spread = InkNoise.value(CGFloat(index) * 0.045, seed: style.seed &+ 40)
                let width = style.weight * (1.25 + 1.4 * spread * spread)
                stroke(from: samples[index - 1], to: samples[index], width: width, color: color, in: &bleed)
            }
        }
    }

    private static func drawBody(_ samples: [CGPoint], style: InkBrushStyle, color: Color, in context: inout GraphicsContext) {
        var layer = context
        layer.opacity = style.bodyOpacity
        layer.drawLayer { body in
            for index in 1..<samples.count {
                let swell = InkNoise.value(CGFloat(index) * 0.02, seed: style.seed)
                let tremor = InkNoise.value(CGFloat(index) * 0.2, seed: style.seed &+ 7)
                let width = style.weight * (0.72 + 0.4 * swell + 0.12 * tremor) * taper(index: index, count: samples.count)
                stroke(from: samples[index - 1], to: samples[index], width: width, color: color, in: &body)
            }
            carveDryStreaks(samples, style: style, in: &body)
        }
    }

    /// Where the brush runs out of ink, the bristles leave thin gaps along the stroke.
    private static func carveDryStreaks(_ samples: [CGPoint], style: InkBrushStyle, in context: inout GraphicsContext) {
        let start = Int(CGFloat(samples.count) * 0.7)
        guard style.weight >= 3, samples.count - start > 4 else { return }
        context.blendMode = .destinationOut
        var random = SeededRandom(seed: style.seed &+ 500)
        for _ in 0..<3 {
            let offset = (random.unit() - 0.5) * style.weight * 0.7
            let from = start + Int(random.unit() * CGFloat(samples.count - start) * 0.4)
            var streak = Path()
            for index in from..<samples.count {
                let normal = unitNormal(from: samples[max(index - 1, 0)], to: samples[min(index + 1, samples.count - 1)])
                let point = CGPoint(x: samples[index].x + normal.x * offset, y: samples[index].y + normal.y * offset)
                if index == from { streak.move(to: point) } else { streak.addLine(to: point) }
            }
            context.stroke(streak, with: .color(.black.opacity(0.4)), lineWidth: 0.5 + random.unit() * 0.5)
        }
        context.blendMode = .normal
    }

    private static func drawFibers(_ samples: [CGPoint], style: InkBrushStyle, color: Color, in context: inout GraphicsContext) {
        var random = SeededRandom(seed: style.seed &+ 90)
        for index in 1..<samples.count where random.unit() < style.fiberChance {
            let normal = unitNormal(from: samples[index - 1], to: samples[index])
            let side: CGFloat = random.unit() < 0.5 ? -1 : 1
            let reach = style.weight * (0.45 + 0.6 * random.unit())
            let trail = reach * 1.6
            let tip = CGPoint(x: samples[index].x + normal.x * reach * side - normal.y * trail, y: samples[index].y + normal.y * reach * side + normal.x * trail)
            stroke(from: samples[index], to: tip, width: max(0.3, style.weight * 0.14), color: color.opacity(0.1 + 0.14 * random.unit()), in: &context)
        }
    }

    private static func drawPool(at point: CGPoint, style: InkBrushStyle, color: Color, in context: inout GraphicsContext) {
        let diameter = style.weight * 1.9
        let halo = diameter * 1.5
        context.fill(Path(ellipseIn: CGRect(x: point.x - halo / 2, y: point.y - halo / 2, width: halo, height: halo)), with: .color(color.opacity(0.08)))
        context.fill(Path(ellipseIn: CGRect(x: point.x - diameter / 2, y: point.y - diameter / 2, width: diameter, height: diameter)), with: .color(color.opacity(0.9)))
    }

    private static func stroke(from start: CGPoint, to end: CGPoint, width: CGFloat, color: Color, in context: inout GraphicsContext) {
        var segment = Path()
        segment.move(to: start)
        segment.addLine(to: end)
        context.stroke(segment, with: .color(color), style: StrokeStyle(lineWidth: width, lineCap: .round))
    }

    private static func taper(index: Int, count: Int) -> CGFloat {
        let remaining = CGFloat(count - index) / CGFloat(count)
        return remaining >= taperShare ? 1 : 0.35 + 0.65 * remaining / taperShare
    }

    private static func unitNormal(from start: CGPoint, to end: CGPoint) -> CGPoint {
        let length = max(hypot(end.x - start.x, end.y - start.y), 0.0001)
        return CGPoint(x: -(end.y - start.y) / length, y: (end.x - start.x) / length)
    }

    static func resample(_ points: [CGPoint]) -> [CGPoint] {
        guard let first = points.first else { return [] }
        var samples = [first]
        for (start, end) in zip(points, points.dropFirst()) {
            let length = hypot(end.x - start.x, end.y - start.y)
            let steps = max(1, Int(length / sampleSpacing))
            for step in 1...steps {
                let share = CGFloat(step) / CGFloat(steps)
                samples.append(CGPoint(x: start.x + (end.x - start.x) * share, y: start.y + (end.y - start.y) * share))
            }
        }
        return samples
    }

    private static func cut(_ samples: [CGPoint], at progress: CGFloat) -> [CGPoint] {
        let clamped = min(max(progress, 0), 1)
        let kept = Int((CGFloat(samples.count) * clamped).rounded(.up))
        return Array(samples.prefix(kept))
    }
}
