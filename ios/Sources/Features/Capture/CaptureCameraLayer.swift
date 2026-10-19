import SwiftUI

/// The full-bleed slot under the capture HUD. The overlay lane's
/// `LiveSceneView(session:model:)` goes in here; until then `CameraPlaceholder` fills it.
struct CaptureCameraLayer<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        content
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.Palette.camera)
            .ignoresSafeArea()
    }
}

/// A dim one-point-perspective room standing in for the camera feed.
struct CameraPlaceholder: View {
    var body: some View {
        Canvas { context, size in
            context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(Theme.Palette.camera))
            let back = CGRect(x: size.width * 0.28, y: size.height * 0.3, width: size.width * 0.44, height: size.height * 0.3)
            context.fill(Path(back), with: .color(Theme.Palette.cameraLine.opacity(0.35)))
            context.stroke(roomLines(size: size, back: back), with: .color(Theme.Palette.cameraLine), lineWidth: 1.5)
            context.fill(counter(size: size, back: back), with: .color(Theme.Palette.cameraLine.opacity(0.6)))
            context.fill(door(back: back, size: size), with: .color(Theme.Palette.cameraLine.opacity(0.5)))
        }
        .accessibilityHidden(true)
    }

    private func roomLines(size: CGSize, back: CGRect) -> Path {
        var path = Path(back)
        let corners = [
            (CGPoint(x: back.minX, y: back.minY), CGPoint(x: 0, y: 0)),
            (CGPoint(x: back.maxX, y: back.minY), CGPoint(x: size.width, y: 0)),
            (CGPoint(x: back.minX, y: back.maxY), CGPoint(x: 0, y: size.height)),
            (CGPoint(x: back.maxX, y: back.maxY), CGPoint(x: size.width, y: size.height)),
        ]
        for (start, end) in corners {
            path.move(to: start)
            path.addLine(to: end)
        }
        return path
    }

    private func counter(size: CGSize, back: CGRect) -> Path {
        Path { path in
            path.move(to: CGPoint(x: back.maxX - back.width * 0.05, y: back.maxY - back.height * 0.38))
            path.addLine(to: CGPoint(x: size.width, y: back.maxY - back.height * 0.1))
            path.addLine(to: CGPoint(x: size.width, y: back.maxY + size.height * 0.18))
            path.addLine(to: CGPoint(x: back.maxX - back.width * 0.05, y: back.maxY))
            path.closeSubpath()
        }
    }

    private func door(back: CGRect, size: CGSize) -> Path {
        Path { path in
            let nearX = back.minX * 0.45
            path.move(to: CGPoint(x: back.minX * 0.82, y: back.minY + back.height * 0.08))
            path.addLine(to: CGPoint(x: nearX, y: back.minY - size.height * 0.04))
            path.addLine(to: CGPoint(x: nearX, y: back.maxY + size.height * 0.12))
            path.addLine(to: CGPoint(x: back.minX * 0.82, y: back.maxY + size.height * 0.02))
            path.closeSubpath()
        }
    }
}

enum SampleSnapshot {
    /// The placeholder room rendered to JPEG, standing in for the last checkpoint's photo.
    static func jpeg(size: CGSize = CGSize(width: 390, height: 844)) -> Data? {
        let renderer = ImageRenderer(content: CameraPlaceholder().frame(width: size.width, height: size.height).brightness(0.12))
        renderer.scale = 2
        return renderer.uiImage?.jpegData(compressionQuality: 0.8)
    }
}
