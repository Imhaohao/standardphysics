import SwiftUI

/// The scanning screen: the camera slot underneath, the HUD on top, and one overlay per phase.
struct CaptureView<Camera: View>: View {
    @Environment(AppModel.self) private var model
    @ViewBuilder let camera: () -> Camera
    @State private var isConfirmingLeave = false

    private var capture: any CaptureControlling { model.capture }

    var body: some View {
        ZStack {
            CaptureCameraLayer(content: camera)
            phaseOverlay
        }
        // A stray finger near an edge shouldn't open Control Center mid-scan; a second swipe still does.
        .defersSystemGestures(on: .all)
        .persistentSystemOverlays(.hidden)
        .sheet(isPresented: roomFinishedBinding) {
            RoomFinishedSheet()
                .environment(\.colorScheme, .light)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
                .interactiveDismissDisabled()
        }
        .confirmationDialog("Leave this scan?", isPresented: $isConfirmingLeave, titleVisibility: .visible) {
            Button("Leave scan") { Task { await model.leaveCapture() } }
            Button("Keep scanning", role: .cancel) {}
        } message: {
            Text("Rooms you've finished stay saved, and you can continue from Your scans.")
        }
    }

    @ViewBuilder private var phaseOverlay: some View {
        switch capture.phase {
        case .scanning(let room):
            ScanningHUD(room: room, onLeave: { isConfirmingLeave = true })
        case .paused(_, let reason):
            PausedOverlay(copy: PauseCopy(reason), onContinue: capture.continueScanning, onLeave: { isConfirmingLeave = true })
        case .relocalizing:
            RelocalizingOverlay(snapshot: capture.relocalizationSnapshot, onRestart: capture.restartRoom, onLeave: { isConfirmingLeave = true })
        case .finishing, .finished:
            ProgressView().tint(Theme.Palette.sheet)
        case .failed(let message):
            CaptureFailedCard(message: message) { model.goHome() }
        case .idle, .betweenRooms:
            Color.clear
        }
    }

    private var roomFinishedBinding: Binding<Bool> {
        Binding(
            get: {
                if case .betweenRooms = capture.phase { return true }
                return false
            },
            set: { _ in }
        )
    }
}

private struct CaptureFailedCard: View {
    let message: String
    let onDone: () -> Void

    var body: some View {
        HUDPanel {
            VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                Text("This scan stopped")
                    .font(Theme.Typography.title)
                Text(message)
                    .font(Theme.Typography.body)
                PrimaryButton(title: "Back to your scans", action: onDone)
            }
        }
        .padding(Theme.Spacing.m)
    }
}
