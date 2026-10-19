import SwiftUI

struct PausedOverlay: View {
    let copy: PauseCopy
    let onContinue: () -> Void
    let onLeave: () -> Void

    var body: some View {
        ZStack(alignment: .bottom) {
            Color.black.opacity(0.5).ignoresSafeArea()
            VStack {
                HStack {
                    Spacer()
                    LeaveScanButton(action: onLeave)
                }
                Spacer()
                HUDPanel(padding: Theme.Spacing.l) {
                    VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                        Image(systemName: copy.systemImage)
                            .font(.system(size: 28, weight: .semibold))
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                            Text(copy.title)
                                .font(Theme.Typography.title)
                                .accessibilityAddTraits(.isHeader)
                            Text(copy.message)
                                .font(Theme.Typography.body)
                                .foregroundStyle(Theme.Palette.sheet.opacity(0.85))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        PrimaryButton(title: "Continue", systemImage: "play.fill", action: onContinue)
                    }
                }
            }
            .padding(.horizontal, Theme.Spacing.m)
            .padding(.bottom, Theme.Spacing.s)
        }
    }
}

/// Shown after a resume while ARKit looks for the saved map. The last checkpoint's picture is
/// laid over the camera so the person can stand where they were and match it.
struct RelocalizingOverlay: View {
    let snapshot: Data?
    let onRestart: () -> Void
    let onLeave: () -> Void

    var body: some View {
        ZStack {
            ghost
            ViewfinderCorners()
                .stroke(Theme.Palette.sheet.opacity(0.9), style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .padding(.horizontal, Theme.Spacing.l)
                .padding(.vertical, 120)
                .accessibilityHidden(true)
            VStack {
                HStack {
                    Spacer()
                    LeaveScanButton(action: onLeave)
                }
                Spacer()
                HUDPanel(padding: Theme.Spacing.l) {
                    VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                        HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s + 4) {
                            ProgressView().tint(Theme.Palette.sheet)
                            Text("Line up this view to pick up where you left off")
                                .font(Theme.Typography.title)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityAddTraits(.isHeader)
                        }
                        Text("Stand where you were when the scan stopped and match the faint picture. Scanning carries on by itself once it lines up.")
                            .font(Theme.Typography.body)
                            .foregroundStyle(Theme.Palette.sheet.opacity(0.85))
                            .fixedSize(horizontal: false, vertical: true)
                        SecondaryButton(title: "Start this room again", systemImage: "arrow.counterclockwise", action: onRestart)
                    }
                }
            }
            .padding(.horizontal, Theme.Spacing.m)
            .padding(.bottom, Theme.Spacing.s)
        }
    }

    @ViewBuilder private var ghost: some View {
        if let snapshot, let image = UIImage(data: snapshot) {
            Color.clear
                .overlay {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                }
                .clipped()
                .opacity(0.45)
                .ignoresSafeArea()
                .accessibilityHidden(true)
        }
    }
}

nonisolated private struct ViewfinderCorners: Shape {
    func path(in rect: CGRect) -> Path {
        let arm: CGFloat = 28
        let corners: [(CGPoint, CGFloat, CGFloat)] = [
            (CGPoint(x: rect.minX, y: rect.minY), 1, 1),
            (CGPoint(x: rect.maxX, y: rect.minY), -1, 1),
            (CGPoint(x: rect.minX, y: rect.maxY), 1, -1),
            (CGPoint(x: rect.maxX, y: rect.maxY), -1, -1),
        ]
        return Path { path in
            for (corner, dx, dy) in corners {
                path.move(to: CGPoint(x: corner.x + arm * dx, y: corner.y))
                path.addLine(to: corner)
                path.addLine(to: CGPoint(x: corner.x, y: corner.y + arm * dy))
            }
        }
    }
}
