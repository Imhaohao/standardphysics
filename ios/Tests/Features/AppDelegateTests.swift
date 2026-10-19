import XCTest
@testable import StandardPhysics

private final class RecordingEvents: BackgroundSessionEventHandling, @unchecked Sendable {
    private let identifiers = Locked<[String]>([])
    var received: [String] { identifiers.read { $0 } }

    func handleEventsForBackgroundURLSession(identifier: String, completionHandler: @escaping @MainActor @Sendable () -> Void) {
        identifiers.write { $0.append(identifier) }
    }
}

@MainActor
final class AppDelegateTests: XCTestCase {
    func testUploadSessionEventsGoToTheUploader() {
        let delegate = AppDelegate()
        let events = RecordingEvents()
        delegate.backgroundUploads = { events }
        var completed = false
        delegate.forwardBackgroundEvents(identifier: URLSessionUploadDriver.defaultIdentifier) { completed = true }
        XCTAssertEqual(events.received, [URLSessionUploadDriver.defaultIdentifier])
        XCTAssertFalse(completed, "the uploader calls it once every event is handled")
    }

    func testOtherSessionsCompleteAtOnce() {
        let delegate = AppDelegate()
        let events = RecordingEvents()
        delegate.backgroundUploads = { events }
        var completed = false
        delegate.forwardBackgroundEvents(identifier: "someone.else") { completed = true }
        XCTAssertTrue(completed)
        XCTAssertTrue(events.received.isEmpty)
    }

    func testWithoutAnUploaderTheSystemIsNotLeftWaiting() {
        let delegate = AppDelegate()
        var completed = false
        delegate.forwardBackgroundEvents(identifier: URLSessionUploadDriver.defaultIdentifier) { completed = true }
        XCTAssertTrue(completed)
    }
}
