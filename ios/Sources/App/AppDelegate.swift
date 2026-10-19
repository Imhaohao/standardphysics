import UIKit

nonisolated protocol BackgroundSessionEventHandling: Sendable {
    func handleEventsForBackgroundURLSession(identifier: String, completionHandler: @escaping @MainActor @Sendable () -> Void)
}

extension BackgroundUploader: BackgroundSessionEventHandling {}

/// Builds the app's services at launch, including background launches where iOS wakes the app
/// only to deliver finished uploads and no window ever appears.
final class AppDelegate: NSObject, UIApplicationDelegate {
    lazy var launch = LaunchMode.fromProcess()
    var backgroundUploads: () -> (any BackgroundSessionEventHandling)? = { nil }

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        if case .live(let services) = launch {
            backgroundUploads = { services.uploader }
        }
        return true
    }

    func application(
        _ application: UIApplication,
        handleEventsForBackgroundURLSession identifier: String,
        completionHandler: @escaping () -> Void
    ) {
        // UIKit hands the handler over on the main thread and the uploader only calls it back
        // on the main actor, so it never actually crosses threads.
        nonisolated(unsafe) let complete = completionHandler
        forwardBackgroundEvents(identifier: identifier) { complete() }
    }

    /// iOS waits for the completion handler before suspending the app again, so it is called
    /// right away for sessions this app does not own.
    func forwardBackgroundEvents(identifier: String, completionHandler: @escaping @MainActor @Sendable () -> Void) {
        guard identifier == URLSessionUploadDriver.defaultIdentifier, let uploads = backgroundUploads() else {
            completionHandler()
            return
        }
        uploads.handleEventsForBackgroundURLSession(identifier: identifier, completionHandler: completionHandler)
    }
}
