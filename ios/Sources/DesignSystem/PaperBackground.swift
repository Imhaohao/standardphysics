import SwiftUI

/// Drafting paper: the same minor and major grid the web workspace draws, with a fine grain.
struct PaperBackground: View {
    var showsGrid = true

    var body: some View {
        Canvas(rendersAsynchronously: true) { context, size in
            context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(Theme.Palette.paper))
            if showsGrid {
                drawGrid(in: &context, size: size, spacing: Theme.Grid.minor, color: Theme.Palette.gridMinor)
                drawGrid(in: &context, size: size, spacing: Theme.Grid.major, color: Theme.Palette.gridMajor)
            }
            drawGrain(in: &context, size: size)
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }

    private func drawGrid(in context: inout GraphicsContext, size: CGSize, spacing: CGFloat, color: Color) {
        var path = Path()
        for x in stride(from: spacing, to: size.width, by: spacing) {
            path.move(to: CGPoint(x: x, y: 0))
            path.addLine(to: CGPoint(x: x, y: size.height))
        }
        for y in stride(from: spacing, to: size.height, by: spacing) {
            path.move(to: CGPoint(x: 0, y: y))
            path.addLine(to: CGPoint(x: size.width, y: y))
        }
        context.stroke(path, with: .color(color), lineWidth: Theme.Stroke.hairline)
    }

    private func drawGrain(in context: inout GraphicsContext, size: CGSize) {
        var random = SeededRandom(seed: 0x5EED)
        let count = Int(size.width * size.height * Theme.Grid.grainDensity)
        for _ in 0..<count {
            let point = CGPoint(x: random.unit() * size.width, y: random.unit() * size.height)
            let diameter = 0.4 + random.unit() * 0.9
            let opacity = 0.025 + random.unit() * 0.05
            let speck = Path(ellipseIn: CGRect(x: point.x, y: point.y, width: diameter, height: diameter))
            context.fill(speck, with: .color(Theme.Palette.ink.opacity(opacity)))
        }
    }
}

#Preview {
    PaperBackground()
}
