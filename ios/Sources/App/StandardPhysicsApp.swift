import SwiftUI

@main
struct StandardPhysicsApp: App {
    @State private var launch = LaunchConfiguration.fromProcess()

    var body: some Scene {
        WindowGroup {
            RootView(model: launch.model) { CameraPlaceholder() }
                .environment(\.trayStartsExpanded, launch.trayStartsExpanded)
                .tint(Theme.Palette.accent)
        }
    }
}

struct RootView<Camera: View>: View {
    let model: AppModel
    @ViewBuilder let camera: () -> Camera

    var body: some View {
        Group {
            switch model.route {
            case .home:
                HomeView()
            case .beforeYouScan:
                BeforeYouScanView()
            case .capture:
                CaptureView(camera: camera)
            case .processing:
                ProcessingView()
            case .results(let id):
                ResultsView(reportID: id)
            }
        }
        .environment(model)
        .preferredColorScheme(model.route == .capture ? .dark : .light)
        .animation(Theme.Motion.settle, value: model.route)
    }
}
