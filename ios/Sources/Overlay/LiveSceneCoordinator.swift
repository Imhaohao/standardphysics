import ARKit
import Combine
import RealityKit

/// Owns the overlay entities inside the ARView and re-projects labels every rendered frame.
final class LiveSceneCoordinator {
    static let projectionFrameInterval = 1
    static let meshRefreshFrameInterval = 45
    static let maximumLabelDistance: Float = 8

    let model: LiveSceneModel
    private let renderer = LiveSceneRenderer()
    private let meshTint = MeshTintLayer()
    private let worldAnchor = AnchorEntity(world: .zero)
    private var frameCount = 0
    private var updateSubscription: (any Cancellable)?
    private weak var arView: ARView?

    init(model: LiveSceneModel) {
        self.model = model
    }

    func attach(to arView: ARView) {
        self.arView = arView
        worldAnchor.addChild(renderer.root)
        worldAnchor.addChild(meshTint.root)
        arView.scene.addAnchor(worldAnchor)
        updateSubscription = arView.scene.subscribe(to: SceneEvents.Update.self) { [weak self] _ in
            MainActor.assumeIsolated { self?.renderedFrame() }
        }
    }

    func detach() {
        updateSubscription?.cancel()
        updateSubscription = nil
        worldAnchor.removeFromParent()
    }

    func render(_ shapes: [SceneShape], showsMeshTint: Bool) {
        renderer.apply(shapes)
        meshTint.root.isEnabled = showsMeshTint
    }

    private func renderedFrame() {
        frameCount += 1
        if frameCount.isMultiple(of: Self.projectionFrameInterval) {
            projectLabels()
        }
        if model.showsMeshTint, frameCount.isMultiple(of: Self.meshRefreshFrameInterval) {
            refreshMeshTint()
        }
    }

    private func projectLabels() {
        guard let arView else { return }
        let camera = arView.cameraTransform.matrix
        let placed = LabelProjector.place(model.labels, in: arView.bounds, scale: model.labelScale) { point in
            guard Self.isVisible(point, from: camera) else { return nil }
            return arView.project(point)
        }
        if placed != model.placedLabels {
            model.placedLabels = placed
        }
    }

    private func refreshMeshTint() {
        guard let anchors = arView?.session.currentFrame?.anchors else { return }
        meshTint.refresh(with: anchors.compactMap { $0 as? ARMeshAnchor })
    }

    private static func isVisible(_ point: SIMD3<Float>, from camera: simd_float4x4) -> Bool {
        let position = SIMD3(camera.columns.3.x, camera.columns.3.y, camera.columns.3.z)
        let forward = -SIMD3(camera.columns.2.x, camera.columns.2.y, camera.columns.2.z)
        let offset = point - position
        return simd_dot(offset, forward) > 0 && simd_length(offset) <= maximumLabelDistance
    }
}
