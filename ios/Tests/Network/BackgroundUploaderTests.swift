import XCTest
@testable import StandardPhysics

final class BackgroundUploaderTests: XCTestCase {
    private var directory: URL!
    private var storage: UploadStorage!
    private let config = UploaderConfiguration(partSize: 1000, maxConcurrentParts: 4, maxPartAttempts: 2)

    override func setUpWithError() throws {
        directory = try makeTemporaryDirectory()
        storage = UploadStorage(root: directory.appendingPathComponent("uploads", isDirectory: true))
    }

    override func tearDownWithError() throws { try? FileManager.default.removeItem(at: directory) }

    private func makeUploader(
        api: FakeUploadAPI, session: FakeUploadSession, concurrency: Int = 4, now: Date = fixedNow
    ) -> BackgroundUploader {
        var configuration = config
        configuration.maxConcurrentParts = concurrency
        return BackgroundUploader(
            api: api, ledger: UploadLedger(fileURL: storage.ledgerURL), session: session, storage: storage,
            configuration: configuration, now: { now }, sleep: { _ in }
        )
    }

    private func source(size: Int = 3500, name: String = "room-1.json") throws -> URL {
        try makeRandomFile(in: directory, name: name, size: size)
    }

    private func persistedRecord(_ id: UUID) async -> UploadRecord? {
        await UploadLedger(fileURL: storage.ledgerURL).record(id)
    }

    func testUploadsPartsWithBoundedConcurrencyThenCompletesWithOrderedETags() async throws {
        let api = FakeUploadAPI()
        let session = FakeUploadSession()
        let uploader = makeUploader(api: api, session: session, concurrency: 2)
        await uploader.start()
        let file = try source()

        let id = try await uploader.enqueue(fileURL: file, scanID: "scan-1", contentType: "application/json")
        await eventually { session.started.count == 2 }
        try await Task.sleep(for: .milliseconds(50))
        XCTAssertEqual(session.started.count, 2, "concurrency limit respected")

        session.succeed(partLabel(id, 1))
        session.succeed(partLabel(id, 2))
        await eventually { session.started.count == 4 }
        session.succeed(partLabel(id, 3))
        session.succeed(partLabel(id, 4))
        await eventually { api.completeCalls.count == 1 }

        XCTAssertEqual(api.requestCalls[0].clientFileID, id)
        XCTAssertEqual(api.requestCalls[0].body.sizeBytes, 3500)
        XCTAssertEqual(api.requestCalls[0].body.partSize, 1000)
        XCTAssertEqual(api.completeCalls[0].parts.map(\.partNumber), [1, 2, 3, 4])
        XCTAssertEqual(api.completeCalls[0].parts.map(\.etag), (1...4).map { "\"etag-\($0)\"" })
        let uploaded = session.started.sorted { $0.label < $1.label }.map(\.body).reduce(Data(), +)
        XCTAssertEqual(uploaded, try Data(contentsOf: file))
        await eventually { await uploader.snapshot().files.first?.state == .completed }
        XCTAssertFalse(FileManager.default.fileExists(atPath: storage.stagedFileURL(for: id).path))
    }

    func testRelaunchAfterKillUploadsOnlyMissingPartsAndRefreshesExpiredURLs() async throws {
        let api = FakeUploadAPI()
        let firstSession = FakeUploadSession()
        let firstRun = makeUploader(api: api, session: firstSession)
        await firstRun.start()
        let id = try await firstRun.enqueue(fileURL: try source(), scanID: "scan-1")
        await eventually { firstSession.started.count == 4 }
        firstSession.succeed(partLabel(id, 1))
        firstSession.succeed(partLabel(id, 2))
        await eventually { await self.persistedRecord(id)?.multipart?.parts.filter(\.isComplete).count == 2 }

        let secondSession = FakeUploadSession(alreadyRunning: [LiveUploadTask(id: 77, label: partLabel(id, 3))])
        let laterThanURLExpiry = fixedNow.addingTimeInterval(7200)
        let secondRun = makeUploader(api: api, session: secondSession, now: laterThanURLExpiry)
        await secondRun.start()

        await eventually { secondSession.started.count == 1 }
        XCTAssertEqual(secondSession.startedLabels, [partLabel(id, 4)], "parts 1-2 done, part 3 still running")
        XCTAssertTrue(secondSession.started[0].url.absoluteString.contains("/refreshed/"))
        XCTAssertEqual(api.refreshCalls, [[4]], "only the part that must restart gets a new URL")
        XCTAssertEqual(api.requestCalls.count, 1, "multipart upload is not re-created")

        secondSession.succeed(partLabel(id, 3))
        secondSession.succeed(partLabel(id, 4))
        await eventually { api.completeCalls.count == 1 }
        XCTAssertEqual(api.completeCalls[0].parts.map(\.etag), (1...4).map { "\"etag-\($0)\"" })
    }

    func testRelaunchRestartsPartsWhoseTasksDiedWithTheApp() async throws {
        let api = FakeUploadAPI()
        let firstSession = FakeUploadSession()
        let firstRun = makeUploader(api: api, session: firstSession)
        await firstRun.start()
        let id = try await firstRun.enqueue(fileURL: try source(size: 2000), scanID: "scan-1")
        await eventually { firstSession.started.count == 2 }

        let secondSession = FakeUploadSession()
        await makeUploader(api: api, session: secondSession).start()
        await eventually { secondSession.started.count == 2 }
        XCTAssertEqual(Set(secondSession.startedLabels), [partLabel(id, 1), partLabel(id, 2)])
        XCTAssertTrue(api.refreshCalls.isEmpty, "unexpired URLs are reused")
    }

    func testExpiredGrantedURLsAreRefreshedBeforeFirstUpload() async throws {
        let api = FakeUploadAPI()
        api.urlTimeToLive = 30
        let session = FakeUploadSession()
        let uploader = makeUploader(api: api, session: session)
        await uploader.start()
        _ = try await uploader.enqueue(fileURL: try source(), scanID: "scan-1")
        await eventually { session.started.count == 4 }
        XCTAssertEqual(api.refreshCalls, [[1, 2, 3, 4]])
        XCTAssertTrue(session.started.allSatisfy { $0.url.absoluteString.contains("/refreshed/") })
    }

    func testForbiddenPartMarksURLExpiredAndRefreshesOnlyThatPart() async throws {
        let api = FakeUploadAPI()
        let session = FakeUploadSession()
        let uploader = makeUploader(api: api, session: session)
        await uploader.start()
        let id = try await uploader.enqueue(fileURL: try source(), scanID: "scan-1")
        await eventually { session.started.count == 4 }

        session.finish(partLabel(id, 2), .failed(statusCode: 403, message: "Request has expired"))
        await eventually { session.started.count == 5 }
        XCTAssertEqual(api.refreshCalls, [[2]])
        XCTAssertEqual(session.startedLabels.last, partLabel(id, 2))
        XCTAssertTrue(session.started.last?.url.absoluteString.contains("/refreshed/") ?? false)
    }

    func testPartFailingRepeatedlyFailsFileAndRetryFailedResumes() async throws {
        let api = FakeUploadAPI()
        let session = FakeUploadSession()
        let uploader = makeUploader(api: api, session: session)
        await uploader.start()
        let id = try await uploader.enqueue(fileURL: try source(size: 1500), scanID: "scan-1")
        await eventually { session.started.count == 2 }

        session.finish(partLabel(id, 1), .failed(statusCode: 500, message: "boom"))
        await eventually { session.startedLabels.filter { $0 == partLabel(id, 1) }.count == 2 }
        session.finish(partLabel(id, 1), .failed(statusCode: 500, message: "boom"))
        await eventually { await uploader.snapshot().files.first?.state.failureMessage == "boom" }

        await uploader.retryFailed()
        await eventually { session.startedLabels.filter { $0 == partLabel(id, 1) }.count == 3 }
        session.succeed(partLabel(id, 1))
        session.succeed(partLabel(id, 2))
        await eventually { api.completeCalls.count == 1 }
    }

    func testCancelledTaskIsRestartedWithoutCountingAsFailure() async throws {
        let api = FakeUploadAPI()
        let session = FakeUploadSession()
        let uploader = makeUploader(api: api, session: session)
        await uploader.start()
        let id = try await uploader.enqueue(fileURL: try source(size: 500), scanID: "scan-1")
        await eventually { session.started.count == 1 }
        session.finish(partLabel(id, 1), .cancelled)
        await eventually { session.started.count == 2 }
        let record = await persistedRecord(id)
        XCTAssertEqual(record?.multipart?.parts[0].failureCount, 0)
    }

    func testTransientRequestFailureKeepsFileQueuedAndRetries() async throws {
        let api = FakeUploadAPI()
        api.failNextRequests(with: [.offline, .timedOut])
        let session = FakeUploadSession(autoSucceed: true)
        let uploader = makeUploader(api: api, session: session)
        await uploader.start()
        _ = try await uploader.enqueue(fileURL: try source(size: 500), scanID: "scan-1")
        await eventually { api.completeCalls.count == 1 }
        XCTAssertEqual(api.requestCalls.count, 3)
    }

    func testPermanentRequestFailureMarksFileFailedWithUserMessage() async throws {
        let api = FakeUploadAPI()
        api.failNextRequests(with: [.forbidden])
        let session = FakeUploadSession()
        let uploader = makeUploader(api: api, session: session)
        await uploader.start()
        _ = try await uploader.enqueue(fileURL: try source(size: 500), scanID: "scan-1")
        await eventually { await uploader.snapshot().files.first?.state.failureMessage == APIError.forbidden.userMessage }
        XCTAssertTrue(session.started.isEmpty)
    }

    func testFilesEnqueuedDuringScanAllCompleteAndWaitReturns() async throws {
        let api = FakeUploadAPI()
        let session = FakeUploadSession(autoSucceed: true)
        let uploader = makeUploader(api: api, session: session)
        await uploader.start()
        for index in 1...3 {
            _ = try await uploader.enqueue(fileURL: try source(size: 1200 * index, name: "room-\(index).json"), scanID: "scan-1")
        }
        _ = try await uploader.enqueue(fileURL: try source(size: 300, name: "other.json"), scanID: "scan-2")
        try await uploader.waitUntilFinished(scanID: "scan-1")

        let snapshot = await uploader.snapshot()
        XCTAssertEqual(snapshot.files(forScan: "scan-1").count, 3)
        XCTAssertTrue(snapshot.files(forScan: "scan-1").allSatisfy { $0.state == .completed && $0.fractionCompleted == 1 })
        XCTAssertGreaterThanOrEqual(api.completeCalls.count, 3)
    }

    func testWaitThrowsWhenAFileFailsForGood() async throws {
        let api = FakeUploadAPI()
        api.failNextRequests(with: [.forbidden])
        let uploader = makeUploader(api: api, session: FakeUploadSession())
        await uploader.start()
        _ = try await uploader.enqueue(fileURL: try source(size: 500, name: "bad.json"), scanID: "scan-1")
        do {
            try await uploader.waitUntilFinished(scanID: "scan-1")
            XCTFail("expected failure")
        } catch {
            XCTAssertEqual(error as? UploadError, .fileFailed(name: "bad.json", message: APIError.forbidden.userMessage))
        }
    }

    func testProgressEventsFeedUploadedBytes() async throws {
        let session = FakeUploadSession()
        let uploader = makeUploader(api: FakeUploadAPI(), session: session)
        await uploader.start()
        let id = try await uploader.enqueue(fileURL: try source(size: 2000), scanID: "scan-1")
        await eventually { session.started.count == 2 }
        session.progress(partLabel(id, 1), bytes: 600)
        await eventually { await uploader.snapshot().uploadedBytes == 600 }
        session.succeed(partLabel(id, 2))
        await eventually { await uploader.snapshot().uploadedBytes == 1600 }
    }

    func testLiveTasksWithoutLedgerEntryAreCancelled() async throws {
        let stray = LiveUploadTask(id: 5, label: partLabel(UUID(), 1))
        let session = FakeUploadSession(alreadyRunning: [stray])
        await makeUploader(api: FakeUploadAPI(), session: session).start()
        XCTAssertEqual(session.cancelledIDs, [5])
    }

    func testEmptyFileIsRejected() async throws {
        let uploader = makeUploader(api: FakeUploadAPI(), session: FakeUploadSession())
        let empty = directory.appendingPathComponent("empty.json")
        try Data().write(to: empty)
        do {
            _ = try await uploader.enqueue(fileURL: empty, scanID: "scan-1")
            XCTFail("expected failure")
        } catch {
            XCTAssertEqual(error as? UploadError, .emptyFile)
        }
    }

    func testOriginalMayChangeAfterEnqueueWithoutCorruptingUpload() async throws {
        let session = FakeUploadSession()
        let uploader = makeUploader(api: FakeUploadAPI(), session: session)
        await uploader.start()
        let file = try source(size: 800)
        let original = try Data(contentsOf: file)
        _ = try await uploader.enqueue(fileURL: file, scanID: "scan-1")
        try Data(repeating: 0, count: 800).write(to: file)
        await eventually { session.started.count == 1 }
        XCTAssertEqual(session.started[0].body, original)
    }

    func testBackgroundEventsCompletionHandlerIsForwardedToSession() async throws {
        let session = FakeUploadSession()
        let uploader = makeUploader(api: FakeUploadAPI(), session: session)
        let called = expectation(description: "completion handler")
        uploader.handleEventsForBackgroundURLSession(identifier: "id") { called.fulfill() }
        session.fireBackgroundEventsCompletion()
        await fulfillment(of: [called], timeout: 2)
    }
}
