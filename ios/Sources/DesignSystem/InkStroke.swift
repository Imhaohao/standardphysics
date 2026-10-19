import SwiftUI

/// The brush mark that inks itself onto the paper when it appears. With Reduce Motion on it
/// is simply there.
struct InkStroke: View {
    var path: InkPath = .underline
    var weight: CGFloat = Theme.Stroke.inkWeight
    var color: Color = Theme.Palette.ink
    var seed: UInt64 = 7
    var drawsOnAppear = true
    var delay: Double = Theme.Motion.inkDrawDelay

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var progress: CGFloat = 0

    var body: some View {
        InkStrokeCanvas(path: path, progress: progress, style: InkBrushStyle(weight: weight, seed: seed), color: color)
            .accessibilityHidden(true)
            .onAppear(perform: ink)
    }

    private func ink() {
        guard drawsOnAppear, !reduceMotion else {
            progress = 1
            return
        }
        withAnimation(Theme.Motion.inkDraw.delay(delay)) { progress = 1 }
    }
}

struct InkStrokeCanvas: View, Animatable {
    let path: InkPath
    var progress: CGFloat
    let style: InkBrushStyle
    let color: Color

    nonisolated var animatableData: CGFloat {
        get { progress }
        set { progress = newValue }
    }

    var body: some View {
        Canvas { context, size in
            let inset = style.weight * 2
            let frame = CGRect(origin: .zero, size: size).insetBy(dx: inset, dy: min(inset, size.height / 2))
            InkBrush.draw(points: path.scaled(to: frame), progress: progress, style: style, color: color, in: &context)
        }
    }
}

#Preview {
    VStack(alignment: .leading, spacing: 0) {
        Text("Your scans").font(Theme.Typography.display)
        InkStroke().frame(width: 210, height: 18)
    }
    .padding()
    .background(PaperBackground())
}
