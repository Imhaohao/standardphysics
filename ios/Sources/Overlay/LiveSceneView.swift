import ARKit
import RealityKit
import SwiftUI

/// The camera with what the app understands drawn over it. The capture lane owns and runs `session`.
struct LiveSceneView: View {
    let session: ARSession
    let model: LiveSceneModel
    @ScaledMetric(relativeTo: .callout) private var labelScale: CGFloat = 1

    var body: some View {
        ZStack {
            LiveARViewContainer(session: session, model: model)
            LiveLabelOverlay(labels: model.placedLabels)
        }
        .ignoresSafeArea()
        .onChange(of: labelScale, initial: true) {
            model.labelScale = labelScale
        }
    }
}

struct LiveARViewContainer: UIViewRepresentable {
    let session: ARSession
    let model: LiveSceneModel

    func makeCoordinator() -> LiveSceneCoordinator {
        LiveSceneCoordinator(model: model)
    }

    func makeUIView(context: Context) -> ARView {
        let arView = ARView(frame: .zero, cameraMode: .ar, automaticallyConfigureSession: false)
        arView.session = session
        arView.renderOptions = [
            .disableMotionBlur,
            .disableDepthOfField,
            .disableGroundingShadows,
            .disableCameraGrain,
            .disablePersonOcclusion,
            .disableAREnvironmentLighting,
        ]
        arView.environment.sceneUnderstanding.options = []
        context.coordinator.attach(to: arView)
        return arView
    }

    func updateUIView(_ arView: ARView, context: Context) {
        context.coordinator.render(model.shapes, showsMeshTint: model.showsMeshTint)
    }

    static func dismantleUIView(_ arView: ARView, coordinator: LiveSceneCoordinator) {
        coordinator.detach()
    }
}
