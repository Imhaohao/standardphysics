import Foundation

/// `-screen <name>` boots straight into one screen with the preview controller, for screenshots
/// and UI checks. Without it the app starts at Home.
struct LaunchConfiguration {
    enum Screen: String, CaseIterable {
        case home
        case homeEmpty = "home-empty"
        case before
        case capture
        case tray
        case paused
        case relocalizing
        case thermal
        case roomFinished = "room-finished"
        case processing
        case results
    }

    let model: AppModel
    var trayStartsExpanded = false

    static func fromProcess(arguments: [String] = ProcessInfo.processInfo.arguments) -> LaunchConfiguration {
        guard let flag = arguments.firstIndex(of: "-screen"), arguments.indices.contains(flag + 1),
              let screen = Screen(rawValue: arguments[flag + 1]) else {
            return LaunchConfiguration(model: makeModel())
        }
        return staged(screen)
    }

    static func makeModel(capture: PreviewCaptureController = PreviewCaptureController(), reports: [ScanReport] = [SampleData.completedReport, SampleData.earlierReport]) -> AppModel {
        AppModel(
            capture: capture,
            processor: PreviewScanProcessor(),
            unfinishedScans: [SampleData.unfinishedManifest()],
            reports: reports
        )
    }

    static func staged(_ screen: Screen) -> LaunchConfiguration {
        let capture = PreviewCaptureController(snapshot: SampleSnapshot.jpeg())
        let model = screen == .homeEmpty
            ? AppModel(capture: capture, processor: PreviewScanProcessor())
            : makeModel(capture: capture)
        model.route = route(for: screen)
        stageCapture(capture, for: screen)
        if screen == .processing { model.stageProcessing() }
        return LaunchConfiguration(model: model, trayStartsExpanded: screen == .tray)
    }

    private static func route(for screen: Screen) -> AppRoute {
        switch screen {
        case .home, .homeEmpty: .home
        case .before: .beforeYouScan
        case .capture, .tray, .paused, .relocalizing, .thermal, .roomFinished: .capture
        case .processing: .processing
        case .results: .results(SampleData.completedReport.scanID)
        }
    }

    private static func stageCapture(_ capture: PreviewCaptureController, for screen: Screen) {
        switch screen {
        case .capture, .tray: capture.stage(.scanning(room: 2))
        case .paused: capture.stage(.paused(room: 2, reason: .user))
        case .relocalizing: capture.stage(.relocalizing(room: 3), roomsSaved: 2)
        case .thermal: capture.stage(.paused(room: 2, reason: .thermal))
        case .roomFinished: capture.stage(.betweenRooms(completed: 2), roomsSaved: 2)
        default: break
        }
    }
}
