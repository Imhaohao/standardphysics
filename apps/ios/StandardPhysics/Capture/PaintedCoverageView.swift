import ARKit
import SwiftUI
import UIKit

/// The room painting itself in as it is scanned.
///
/// A flat layer over RoomPlan's own view rather than a second 3D view, so
/// RoomPlan's camera, white outlines and coaching stay visible under it on
/// every iOS version. On each screen refresh the painted cells are projected
/// through the camera of RoomPlan's latest frame, which keeps them on the wall
/// as the phone moves.
///
/// Nothing here drives the session. RoomPlan owns it; this only reads its
/// latest frame.
struct PaintedCoverageView: UIViewRepresentable {
    let session: ARSession
    let paint: [PaintedSample]

    func makeUIView(context: Context) -> PaintOverlayView {
        PaintOverlayView(session: session)
    }

    func updateUIView(_ view: PaintOverlayView, context: Context) {
        view.session = session
        view.show(paint)
    }
}

/// Draws the painted cells as one shape, redrawn once per screen refresh.
final class PaintOverlayView: UIView {
    var session: ARSession
    private var cells: [PaintCell] = []
    private var shown: [PaintedSample] = []
    private let shape = CAShapeLayer()
    private var displayLink: CADisplayLink?

    init(session: ARSession) {
        self.session = session
        super.init(frame: .zero)
        isUserInteractionEnabled = false
        backgroundColor = .clear
        shape.fillColor = UIColor(AppTheme.scanLine).withAlphaComponent(0.55).cgColor
        shape.actions = ["path": NSNull()]
        layer.addSublayer(shape)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { nil }

    /// Rebuilds the cells only when the paint changed, because coverage
    /// arrives twice a second and the cells should not be remade every frame.
    func show(_ paint: [PaintedSample]) {
        guard paint != shown else { return }
        shown = paint
        cells = paint.filter(\.isObserved).map(PaintCell.init)
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        shape.frame = bounds
    }

    /// The refresh runs only while the view is on screen, which also ends the
    /// display link's hold on this view once the walk closes.
    override func didMoveToWindow() {
        super.didMoveToWindow()
        displayLink?.invalidate()
        displayLink = nil
        guard window != nil else { return }
        let link = CADisplayLink(target: self, selector: #selector(redraw))
        link.preferredFrameRateRange = CAFrameRateRange(minimum: 30, maximum: 60, preferred: 60)
        link.add(to: .main, forMode: .common)
        displayLink = link
    }

    @objc private func redraw() {
        guard let camera = session.currentFrame?.camera, bounds.width > 0 else { return }
        let orientation = window?.windowScene?.interfaceOrientation ?? .portrait
        shape.path = PaintProjection(camera: camera, orientation: orientation, viewport: bounds.size).path(for: cells)
    }
}

/// One painted cell: a square a hand's width across, lying on its surface.
struct PaintCell: Equatable {
    /// A hand's width, so a wall fills in at about the pace someone walks.
    static let side: Float = 0.18

    let corners: [SIMD3<Float>]

    init(_ sample: PaintedSample) {
        let facing = simd_quatf(from: SIMD3<Float>(0, 0, 1), to: simd_normalize(sample.worldNormal))
        let across = facing.act(SIMD3<Float>(1, 0, 0)) * Self.side / 2
        let up = facing.act(SIMD3<Float>(0, 1, 0)) * Self.side / 2
        let center = sample.worldPoint
        corners = [center - across - up, center + across - up, center + across + up, center - across + up]
    }
}

/// Where one camera puts points of the world on the screen.
struct PaintProjection {
    let worldToClip: simd_float4x4
    let viewport: CGSize

    init(worldToClip: simd_float4x4, viewport: CGSize) {
        self.worldToClip = worldToClip
        self.viewport = viewport
    }

    init(camera: ARCamera, orientation: UIInterfaceOrientation, viewport: CGSize) {
        let view = camera.viewMatrix(for: orientation)
        let projection = camera.projectionMatrix(for: orientation, viewportSize: viewport, zNear: 0.01, zFar: 100)
        self.init(worldToClip: projection * view, viewport: viewport)
    }

    /// Every cell wholly in front of the camera, one closed shape each.
    func path(for cells: [PaintCell]) -> CGPath {
        let path = CGMutablePath()
        for cell in cells {
            guard let points = screenPoints(of: cell.corners) else { continue }
            path.addLines(between: points)
            path.closeSubpath()
        }
        return path
    }

    /// The corners on screen, or nil when any corner is behind the camera.
    func screenPoints(of corners: [SIMD3<Float>]) -> [CGPoint]? {
        var points: [CGPoint] = []
        points.reserveCapacity(corners.count)
        for corner in corners {
            guard let point = screenPoint(of: corner) else { return nil }
            points.append(point)
        }
        return points
    }

    func screenPoint(of world: SIMD3<Float>) -> CGPoint? {
        let clip = worldToClip * SIMD4<Float>(world, 1)
        guard clip.w > 0.01 else { return nil }
        let x = (clip.x / clip.w + 1) / 2 * Float(viewport.width)
        let y = (1 - clip.y / clip.w) / 2 * Float(viewport.height)
        return CGPoint(x: CGFloat(x), y: CGFloat(y))
    }
}
