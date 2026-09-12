import SwiftUI
import simd

struct CaptureScreen: View {
    @ObservedObject var model: AppModel
    @StateObject private var capture = CaptureSessionStore()

    var body: some View {
        ZStack {
            RoomCaptureContainer(store: capture).ignoresSafeArea()
            LinearGradient(
                colors: [.black.opacity(0.56), .clear, .black.opacity(0.5)],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
            .allowsHitTesting(false)

            VStack(spacing: 16) {
                captureHeader
                Spacer()
                if capture.phase == .scanning {
                    GuidanceArrow(angle: capture.coverage.unfinishedDirection.radians)
                }
                CoverageMapView(surfaces: capture.surfaces, coverage: capture.coverage)
                    .frame(height: 136)
                finishButton
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
        .onChange(of: capture.phase) { _, phase in
            if phase == .ready, let scan = capture.capturedScan {
                model.screen = .review(scan)
            }
        }
    }

    private var captureHeader: some View {
        HStack(spacing: 14) {
            Button {
                capture.cancel()
                model.showStart()
            } label: {
                Image(systemName: "xmark")
                    .font(.headline)
                    .frame(width: 44, height: 44)
                    .background(.black.opacity(0.58))
                    .clipShape(Circle())
            }
            .foregroundStyle(.white)
            .accessibilityLabel("Cancel scan")

            Text(capture.instruction)
                .font(.headline)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 18)
                .frame(minHeight: 52)
                .background(.black.opacity(0.58))
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
    }

    @ViewBuilder private var finishButton: some View {
        switch capture.phase {
        case .processing:
            ProgressView()
                .tint(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 18)
                .background(.black.opacity(0.72))
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        case .failed(let message):
            Text(message)
                .font(.headline)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .padding(18)
                .background(AppTheme.warning)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        default:
            Button("Done") { capture.finish() }
                .buttonStyle(PrimaryButtonStyle())
        }
    }
}

private struct GuidanceArrow: View {
    let angle: Double

    var body: some View {
        Image(systemName: "arrow.up")
            .font(.system(size: 34, weight: .bold))
            .foregroundStyle(.white)
            .frame(width: 68, height: 68)
            .background(AppTheme.accent.opacity(0.9))
            .clipShape(Circle())
            .rotationEffect(.radians(angle))
            .animation(.easeOut(duration: 0.25), value: angle)
            .accessibilityLabel("Turn toward the unfinished wall")
    }
}

private struct CoverageMapView: View {
    let surfaces: [SurfaceSnapshot]
    let coverage: CoverageSnapshot
    @State private var pulse = false

    var body: some View {
        Canvas { context, size in
            let coverageByID = Dictionary(uniqueKeysWithValues: coverage.surfaces.map { ($0.id, $0) })
            let walls = surfaces.filter(\.isWall)
            let points = walls.flatMap(endpoints)
            guard let bounds = MapBounds(points: points) else { return }

            for surface in walls {
                let line = endpoints(surface)
                guard line.count == 2 else { continue }
                var path = Path()
                path.move(to: bounds.project(line[0], into: size))
                path.addLine(to: bounds.project(line[1], into: size))
                let isDone = coverageByID[surface.id]?.isDone == true
                context.stroke(
                    path,
                    with: .color(isDone ? AppTheme.scanLine : .white.opacity(pulse ? 0.9 : 0.4)),
                    style: StrokeStyle(lineWidth: isDone ? 7 : 4, lineCap: .round, dash: isDone ? [] : [7, 7])
                )
            }
        }
        .padding(18)
        .background(.black.opacity(0.62))
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .onAppear {
            withAnimation(.easeInOut(duration: 1).repeatForever(autoreverses: true)) { pulse.toggle() }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(coverage.isComplete ? "The room is covered" : "Room coverage map")
    }

    private func endpoints(_ surface: SurfaceSnapshot) -> [SIMD2<Float>] {
        let left = surface.transform * SIMD4(-surface.width / 2, 0, 0, 1)
        let right = surface.transform * SIMD4(surface.width / 2, 0, 0, 1)
        return [SIMD2(left.x, left.z), SIMD2(right.x, right.z)]
    }
}

private struct MapBounds {
    let minX: Float
    let maxX: Float
    let minY: Float
    let maxY: Float

    init?(points: [SIMD2<Float>]) {
        guard let first = points.first else { return nil }
        minX = points.reduce(first.x) { min($0, $1.x) }
        maxX = points.reduce(first.x) { max($0, $1.x) }
        minY = points.reduce(first.y) { min($0, $1.y) }
        maxY = points.reduce(first.y) { max($0, $1.y) }
    }

    func project(_ point: SIMD2<Float>, into size: CGSize) -> CGPoint {
        let width = max(maxX - minX, 0.5)
        let height = max(maxY - minY, 0.5)
        return CGPoint(
            x: CGFloat((point.x - minX) / width) * size.width,
            y: CGFloat((point.y - minY) / height) * size.height
        )
    }
}
