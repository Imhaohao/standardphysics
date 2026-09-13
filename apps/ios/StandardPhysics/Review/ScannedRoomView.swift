import SceneKit
import SwiftUI

struct ScannedRoomView: UIViewRepresentable {
    let scene: SCNScene?
    let locator: ScanObjectLocator
    let onSelect: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(parent: self) }

    func makeUIView(context: Context) -> SCNView {
        let view = SCNView()
        view.allowsCameraControl = true
        view.autoenablesDefaultLighting = true
        view.backgroundColor = UIColor(AppTheme.panel)
        view.accessibilityLabel = "Scanned room. Drag to rotate. Pinch to zoom."
        view.addGestureRecognizer(UITapGestureRecognizer(target: context.coordinator,
            action: #selector(Coordinator.selectSurface(_:))))
        return view
    }

    func updateUIView(_ view: SCNView, context: Context) {
        context.coordinator.parent = self
        if view.scene !== scene { view.scene = scene }
    }

    @MainActor final class Coordinator: NSObject {
        var parent: ScannedRoomView
        init(parent: ScannedRoomView) { self.parent = parent }

        @objc func selectSurface(_ gesture: UITapGestureRecognizer) {
            guard let view = gesture.view as? SCNView,
                  let hit = view.hitTest(gesture.location(in: view)).first else { return }
            let point = SIMD3<Float>(hit.worldCoordinates.x, hit.worldCoordinates.y, hit.worldCoordinates.z)
            parent.onSelect(parent.locator.object(at: point)?.friendlyName.capitalized ?? "Scanned surface")
        }
    }
}
