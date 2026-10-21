import SwiftUI

@main
struct StandardPhysicsApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @Environment(\.scenePhase) private var scenePhase

    private var launch: LaunchMode { delegate.launch }

    var body: some Scene {
        WindowGroup {
            content
                .tint(Theme.Palette.accent)
        }
        .onChange(of: scenePhase) { _, phase in
            guard case .live(let services) = launch else { return }
            services.coordinator.handleScenePhase(phase)
        }
    }

    @ViewBuilder private var content: some View {
        switch launch {
        case .staged(let configuration):
            RootView(model: configuration.model) { CameraPlaceholder() }
                .environment(\.trayStartsExpanded, configuration.trayStartsExpanded)
        case .live(let services):
            RootView(model: services.appModel) { LiveCameraLayer(services: services) }
                .task {
                    await services.appModel.account.restore()
                    await services.appModel.refresh()
                }
        }
    }
}

/// Screenshots and unit tests run on staged data; everything else runs the real capture stack.
enum LaunchMode {
    case staged(LaunchConfiguration)
    case live(LiveServices)

    @MainActor
    static func fromProcess(_ process: ProcessInfo = .processInfo) -> LaunchMode {
        let isUnderTest = process.environment["XCTestConfigurationFilePath"] != nil
        if isUnderTest || process.arguments.contains("-screen") {
            return .staged(LaunchConfiguration.fromProcess(arguments: process.arguments))
        }
        return .live(LiveServices())
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
        .sensoryFeedback(trigger: model.route) { old, new in
            HapticMoment.forRoute(from: old, to: new)?.feedback
        }
        .preferredColorScheme(model.route == .capture ? .dark : .light)
        .animation(Theme.Motion.settle, value: model.route)
    }
}
