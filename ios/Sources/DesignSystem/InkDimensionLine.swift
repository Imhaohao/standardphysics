import SwiftUI

/// A drafting dimension: an inked run between two extension lines, closed with slash ticks.
/// It fills its frame horizontally; `span` picks the part of the width it covers.
struct InkDimensionLine: View {
    var span: ClosedRange<CGFloat> = 0...1
    var color: Color = Theme.Palette.ink
    var seed: UInt64 = 11
    var drawsOnAppear = true

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var progress: CGFloat = 0

    var body: some View {
        InkDimensionCanvas(span: span, progress: progress, color: color, seed: seed)
            .accessibilityHidden(true)
            .onAppear {
                guard drawsOnAppear, !reduceMotion else {
                    progress = 1
                    return
                }
                withAnimation(Theme.Motion.inkDraw.delay(Theme.Motion.inkDrawDelay)) { progress = 1 }
            }
    }
}

private struct InkDimensionCanvas: View, Animatable {
    let span: ClosedRange<CGFloat>
    var progress: CGFloat
    let color: Color
    let seed: UInt64

    nonisolated var animatableData: CGFloat {
        get { progress }
        set { progress = newValue }
    }

    var body: some View {
        Canvas { context, size in
            let midY = size.height / 2
            let tick = min(size.height / 2, 6)
            let startX = max(tick, size.width * span.lowerBound)
            let endX = min(size.width - tick, size.width * span.upperBound)
            let fine = InkBrushStyle(weight: Theme.Stroke.inkFine, seed: seed, fiberChance: 0.04, pooledStart: false)
            for x in [startX, endX] {
                let extensionLine = [CGPoint(x: x, y: midY - tick * 1.6), CGPoint(x: x, y: midY + tick * 1.6)]
                InkBrush.draw(points: extensionLine, progress: 1, style: fine, color: color.opacity(0.55), in: &context)
            }
            let run = [CGPoint(x: startX, y: midY), CGPoint(x: endX, y: midY)]
            InkBrush.draw(points: run, progress: progress, style: InkBrushStyle(weight: Theme.Stroke.inkFine * 1.3, seed: seed), color: color, in: &context)
            guard progress >= 1 else { return }
            for x in [startX, endX] {
                let slash = [CGPoint(x: x - tick * 0.8, y: midY + tick * 0.8), CGPoint(x: x + tick * 0.8, y: midY - tick * 0.8)]
                InkBrush.draw(points: slash, progress: 1, style: InkBrushStyle(weight: Theme.Stroke.inkFine * 1.4, seed: seed &+ 3, pooledStart: false), color: color, in: &context)
            }
        }
    }
}

#Preview {
    InkDimensionLine(span: 0.1...0.8)
        .frame(height: 24)
        .padding()
        .background(PaperBackground())
}
