import Foundation

/// Uploads files to presigned multipart URLs through a background URLSession so transfers
/// continue after the app is suspended or killed. The ledger is the source of truth: on every
/// launch `start()` rebuilds in-memory state from the ledger plus the session's live tasks and
/// uploads only the parts that are neither finished nor running.
actor BackgroundUploader {
    private let api: any UploadAPI
    private let ledger: UploadLedger
    private let session: any UploadTaskSession
    private let storage: UploadStorage
    private let slicer: PartSlicer
    private let configuration: UploaderConfiguration
    private let now: @Sendable () -> Date
    private let sleep: Sleeper

    private var inFlight: [PartKey: Int] = [:]
    private var sentBytes: [PartKey: Int64] = [:]
    private var subscribers: [UUID: AsyncStream<UploadSnapshot>.Continuation] = [:]
    private var eventTask: Task<Void, Never>?
    private var repumpTask: Task<Void, Never>?
    private var isPumping = false
    private var pumpRequested = false
    private var transientFailureCount = 0
    private var emitTicket = 0
    private var lastProgressEmit = Date.distantPast
    private var persistenceError: String?

    init(
        api: any UploadAPI,
        ledger: UploadLedger,
        session: any UploadTaskSession,
        storage: UploadStorage,
        slicer: PartSlicer = PartSlicer(),
        configuration: UploaderConfiguration = UploaderConfiguration(),
        now: @escaping @Sendable () -> Date = { Date() },
        sleep: @escaping Sleeper = DefaultSleeper.sleep
    ) {
        self.api = api
        self.ledger = ledger
        self.session = session
        self.storage = storage
        self.slicer = slicer
        self.configuration = configuration
        self.now = now
        self.sleep = sleep
    }

    static func makeDefault(api: any UploadAPI) throws -> BackgroundUploader {
        let storage = try UploadStorage.applicationSupport()
        return BackgroundUploader(
            api: api, ledger: UploadLedger(fileURL: storage.ledgerURL),
            session: URLSessionUploadDriver(), storage: storage
        )
    }

    // MARK: Public API

    /// Call once at launch (including background launches) before anything else.
    func start() async {
        beginConsumingEvents()
        await adoptLiveTasks()
        requestPump()
    }

    /// Copies the file (an APFS clone, so cheap) and queues it. The copy means the caller may
    /// keep appending to or deleting the original, e.g. a mesh checkpoint, without corrupting parts.
    @discardableResult
    func enqueue(fileURL: URL, scanID: String, contentType: String = "application/octet-stream") async throws -> UUID {
        let size = try fileSize(of: fileURL)
        guard size > 0 else { throw UploadError.emptyFile }
        let id = UUID()
        try await storage.stage(fileURL, as: id)
        let record = UploadRecord(
            id: id, scanID: scanID, fileName: fileURL.lastPathComponent, contentType: contentType,
            sizeBytes: size, enqueuedAt: now(), state: .queued, multipart: nil
        )
        try await ledger.insert(record)
        await emit()
        requestPump()
        return id
    }

    func updates() async -> AsyncStream<UploadSnapshot> {
        let id = UUID()
        let (stream, continuation) = AsyncStream.makeStream(of: UploadSnapshot.self, bufferingPolicy: .bufferingNewest(1))
        subscribers[id] = continuation
        continuation.onTermination = { [weak self] _ in
            Task { await self?.removeSubscriber(id) }
        }
        continuation.yield(await buildSnapshot())
        return stream
    }

    func snapshot() async -> UploadSnapshot {
        await buildSnapshot()
    }

    /// Returns when every file of the scan is uploaded; throws if one failed for good.
    func waitUntilFinished(scanID: String) async throws {
        for await snapshot in await updates() {
            let files = snapshot.files(forScan: scanID)
            if let failure = files.first(where: { $0.state.failureMessage != nil }) {
                throw UploadError.fileFailed(name: failure.fileName, message: failure.state.failureMessage ?? "")
            }
            if files.allSatisfy({ $0.state == .completed }) { return }
        }
    }

    func retryFailed(scanID: String? = nil) async {
        for record in await ledger.all() {
            guard case .failed = record.state, scanID == nil || record.scanID == scanID else { continue }
            await resetFailedRecord(record.id)
        }
        requestPump()
    }

    func removeFinished(scanID: String) async {
        let finished = await ledger.all().filter { $0.scanID == scanID && $0.state == .completed }
        await persist { try await self.ledger.remove(finished.map(\.id)) }
        await emit()
    }

    nonisolated func handleEventsForBackgroundURLSession(
        identifier: String, completionHandler: @escaping @MainActor @Sendable () -> Void
    ) {
        session.setBackgroundEventsCompletion { Task { @MainActor in completionHandler() } }
    }

    // MARK: Event handling

    private func beginConsumingEvents() {
        guard eventTask == nil else { return }
        let events = session.events
        eventTask = Task { [weak self] in
            for await event in events {
                await self?.handle(event)
            }
        }
    }

    private func adoptLiveTasks() async {
        let records = Dictionary(uniqueKeysWithValues: await ledger.all().map { ($0.id, $0) })
        for task in await session.liveTasks() {
            if let key = PartKey(label: task.label), isPartPending(key, in: records) {
                inFlight[key] = task.id
            } else {
                await session.cancelTask(id: task.id)
            }
        }
    }

    private func isPartPending(_ key: PartKey, in records: [UUID: UploadRecord]) -> Bool {
        guard let record = records[key.fileID], record.state.isActive,
              let part = record.multipart?.parts.first(where: { $0.number == key.number }) else { return false }
        return !part.isComplete
    }

    private func handle(_ event: UploadTaskEvent) async {
        switch event {
        case .progress(let label, let bytes):
            await recordProgress(label: label, bytes: bytes)
        case .finished(let label, let outcome):
            guard let key = PartKey(label: label) else { return }
            await finish(key, outcome)
        }
    }

    private func recordProgress(label: String, bytes: Int64) async {
        guard let key = PartKey(label: label) else { return }
        sentBytes[key] = bytes
        guard now().timeIntervalSince(lastProgressEmit) > 0.25 else { return }
        lastProgressEmit = now()
        await emit()
    }

    /// The part stays marked in flight until the ledger reflects the outcome. Releasing it
    /// earlier would let a concurrent pump see "not done, not running" and start it twice.
    private func finish(_ key: PartKey, _ outcome: UploadTaskOutcome) async {
        let retryImmediately = await apply(outcome, to: key)
        inFlight[key] = nil
        sentBytes[key] = nil
        await emit()
        if retryImmediately { requestPump() } else { scheduleRepump() }
    }

    private func apply(_ outcome: UploadTaskOutcome, to key: PartKey) async -> Bool {
        switch outcome {
        case .succeeded(let etag?) where !etag.isEmpty:
            await markPartUploaded(key, etag: etag)
            return true
        case .succeeded:
            await recordPartFailure(key, statusCode: nil, message: "The storage service did not return an ETag")
        case .failed(let statusCode, let message):
            await recordPartFailure(key, statusCode: statusCode, message: message)
        case .cancelled:
            break
        }
        return false
    }

    private func markPartUploaded(_ key: PartKey, etag: String) async {
        await persist {
            try await self.ledger.update(key.fileID) { record in
                record.multipart?.updatePart(key.number) { $0.etag = etag }
            }
        }
        storage.removePartFile(for: key.fileID, partNumber: key.number)
        transientFailureCount = 0
    }

    private func recordPartFailure(_ key: PartKey, statusCode: Int?, message: String) async {
        let limit = configuration.maxPartAttempts
        await persist {
            try await self.ledger.update(key.fileID) { record in
                record.multipart?.updatePart(key.number) { part in
                    part.failureCount += 1
                    if statusCode == 403 { part.expiresAt = .distantPast }
                }
                let attempts = record.multipart?.parts.first { $0.number == key.number }?.failureCount ?? 0
                if attempts >= limit { record.state = .failed(message: message) }
            }
        }
    }

    // MARK: Pump

    private func requestPump() {
        pumpRequested = true
        guard !isPumping else { return }
        isPumping = true
        Task { await self.runPumpLoop() }
    }

    private func runPumpLoop() async {
        while pumpRequested {
            pumpRequested = false
            for record in await ledger.all() where record.state.isActive {
                await advance(record.id)
            }
        }
        isPumping = false
    }

    private func scheduleRepump() {
        guard repumpTask == nil else { return }
        let delay = configuration.retryBackoff.delay(forAttempt: transientFailureCount)
        transientFailureCount += 1
        repumpTask = Task { [weak self, sleep] in
            try? await sleep(delay)
            await self?.repumpFired()
        }
    }

    private func repumpFired() {
        repumpTask = nil
        requestPump()
    }

    private func advance(_ id: UUID) async {
        do {
            guard var record = await ledger.record(id), record.state.isActive else { return }
            if record.multipart == nil { record = try await beginMultipart(record) }
            try await uploadMissingParts(of: record)
            try await completeIfFinished(id)
        } catch {
            await handleStepFailure(error, id: id)
        }
    }

    private func beginMultipart(_ record: UploadRecord) async throws -> UploadRecord {
        let body = RequestUploadBody(
            fileName: record.fileName, contentType: record.contentType,
            sizeBytes: record.sizeBytes, partSize: configuration.partSize
        )
        let grant = try await api.requestUpload(scanID: record.scanID, file: body, clientFileID: record.id)
        let expected = PartSlicer.partCount(fileSize: record.sizeBytes, partSize: grant.partSize)
        guard grant.partSize > 0, grant.parts.count == expected else { throw APIError.malformedResponse }
        let multipart = MultipartSession(
            uploadID: grant.uploadID, partSize: grant.partSize,
            parts: grant.parts.sorted { $0.partNumber < $1.partNumber }
                .map { UploadPart(number: $0.partNumber, url: $0.url, expiresAt: $0.expiresAt) }
        )
        let updated = try await ledger.update(record.id) {
            $0.multipart = multipart
            $0.state = .uploading
        }
        await emit()
        return updated ?? record
    }

    private func uploadMissingParts(of record: UploadRecord) async throws {
        guard let missing = missingParts(of: record), !missing.isEmpty else { return }
        let fresh = try await refreshExpiredURLs(of: record, among: missing)
        for part in fresh where inFlight.count < configuration.maxConcurrentParts {
            try await startUpload(of: part, in: record)
        }
    }

    private func missingParts(of record: UploadRecord) -> [UploadPart]? {
        record.multipart?.parts.filter { !$0.isComplete && inFlight[PartKey(fileID: record.id, number: $0.number)] == nil }
    }

    private func refreshExpiredURLs(of record: UploadRecord, among missing: [UploadPart]) async throws -> [UploadPart] {
        let expired = missing.filter { $0.isExpired(at: now(), skew: configuration.urlExpirySkew) }
        guard !expired.isEmpty, let multipart = record.multipart else { return missing }
        let replacements = try await api.refreshPartURLs(
            scanID: record.scanID, uploadID: multipart.uploadID, partNumbers: expired.map(\.number)
        )
        let byNumber = Dictionary(replacements.map { ($0.partNumber, $0) }, uniquingKeysWith: { $1 })
        let updated = try await ledger.update(record.id) { record in
            for (number, replacement) in byNumber {
                record.multipart?.updatePart(number) {
                    $0.url = replacement.url
                    $0.expiresAt = replacement.expiresAt
                }
            }
        }
        return updated.flatMap(missingParts(of:)) ?? missing
    }

    private func startUpload(of part: UploadPart, in record: UploadRecord) async throws {
        guard let partSize = record.multipart?.partSize else { return }
        let key = PartKey(fileID: record.id, number: part.number)
        let partFile = storage.partFileURL(for: record.id, partNumber: part.number)
        _ = try await slicer.slice(
            source: storage.stagedFileURL(for: record.id), partNumber: part.number, partSize: partSize, to: partFile
        )
        var request = URLRequest(url: part.url)
        request.httpMethod = "PUT"
        inFlight[key] = session.startUpload(request: request, fileURL: partFile, label: key.label)
    }

    private func completeIfFinished(_ id: UUID) async throws {
        guard let record = await ledger.record(id), let multipart = record.multipart, record.state.isActive,
              multipart.parts.allSatisfy(\.isComplete) else { return }
        try await ledger.update(id) { $0.state = .completing }
        let parts = multipart.parts.compactMap { part in part.etag.map { CompletedPart(partNumber: part.number, etag: $0) } }
        try await api.completeUpload(scanID: record.scanID, uploadID: multipart.uploadID, parts: parts)
        try await ledger.update(id) { $0.state = .completed }
        storage.removeFiles(for: id)
        transientFailureCount = 0
        await emit()
    }

    private func handleStepFailure(_ error: Error, id: UUID) async {
        let apiError = (error as? APIError) ?? APIError(transportError: error)
        switch recovery(for: apiError, isStorageError: !(error is APIError) && !(error is URLError)) {
        case .retryLater:
            scheduleRepump()
        case .restartUpload:
            await restartUpload(id)
        case .giveUp:
            await markFailed(id, message: apiError.userMessage)
        }
    }

    private enum Recovery { case retryLater, restartUpload, giveUp }

    private func recovery(for error: APIError, isStorageError: Bool) -> Recovery {
        if isStorageError { return .giveUp }
        if error == .notFound { return .restartUpload }
        if error.isTransient || error == .unauthorized || error == .cancelled { return .retryLater }
        return .giveUp
    }

    /// The server forgot the multipart upload (expired or aborted), so every part starts over.
    private func restartUpload(_ id: UUID) async {
        let record = await ledger.record(id)
        for number in record?.multipart?.parts.map(\.number) ?? [] {
            let key = PartKey(fileID: id, number: number)
            if let taskID = inFlight.removeValue(forKey: key) { await session.cancelTask(id: taskID) }
        }
        await persist {
            try await self.ledger.update(id) {
                $0.multipart = nil
                $0.state = .queued
            }
        }
        scheduleRepump()
    }

    private func markFailed(_ id: UUID, message: String) async {
        await persist { try await self.ledger.update(id) { $0.state = .failed(message: message) } }
        await emit()
    }

    private func resetFailedRecord(_ id: UUID) async {
        await persist {
            try await self.ledger.update(id) { record in
                let numbers = record.multipart?.parts.map(\.number) ?? []
                numbers.forEach { number in record.multipart?.updatePart(number) { $0.failureCount = 0 } }
                record.state = record.multipart == nil ? .queued : .uploading
            }
        }
        await emit()
    }

    // MARK: Snapshots

    private func persist<T>(_ work: () async throws -> T) async {
        do {
            _ = try await work()
            persistenceError = nil
        } catch {
            persistenceError = error.localizedDescription
        }
    }

    private func emit() async {
        emitTicket += 1
        let ticket = emitTicket
        let snapshot = await buildSnapshot()
        guard ticket == emitTicket else { return }
        subscribers.values.forEach { $0.yield(snapshot) }
    }

    private func buildSnapshot() async -> UploadSnapshot {
        let files = await ledger.all().map(status(for:))
        return UploadSnapshot(files: files, persistenceError: persistenceError)
    }

    private func status(for record: UploadRecord) -> UploadFileStatus {
        UploadFileStatus(
            id: record.id, scanID: record.scanID, fileName: record.fileName, state: record.state,
            totalBytes: record.sizeBytes, uploadedBytes: uploadedBytes(of: record)
        )
    }

    private func uploadedBytes(of record: UploadRecord) -> Int64 {
        if record.state == .completed { return record.sizeBytes }
        guard let multipart = record.multipart else { return 0 }
        let uploaded = multipart.parts.reduce(Int64(0)) { total, part in
            let key = PartKey(fileID: record.id, number: part.number)
            let length = PartSlicer.partLength(partNumber: part.number, fileSize: record.sizeBytes, partSize: multipart.partSize)
            return total + (part.isComplete ? length : min(length, sentBytes[key] ?? 0))
        }
        return min(uploaded, record.sizeBytes)
    }

    private func removeSubscriber(_ id: UUID) {
        subscribers[id] = nil
    }

    private func fileSize(of url: URL) throws -> Int64 {
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        return (attributes[.size] as? NSNumber)?.int64Value ?? 0
    }
}

nonisolated extension MultipartSession {
    mutating func updatePart(_ number: Int, _ change: (inout UploadPart) -> Void) {
        guard let index = parts.firstIndex(where: { $0.number == number }) else { return }
        change(&parts[index])
    }
}
