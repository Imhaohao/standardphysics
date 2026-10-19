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
    private var reconciled: Set<UUID> = []

    /// S3's own limit; a server asking for more parts than this is broken or hostile.
    static let maximumPartCount = 10_000

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
    func enqueue(
        fileURL: URL, scanID: String, kind: UploadKind = .artifact, contentType: String = "application/octet-stream"
    ) async throws -> UUID {
        let size = try fileSize(of: fileURL)
        guard size > 0 else { throw UploadError.emptyFile }
        let id = UUID()
        try await storage.stage(fileURL, as: id)
        let digest = try await FileDigest.sha256Hex(of: storage.stagedFileURL(for: id))
        let record = UploadRecord(
            id: id, scanID: scanID, fileName: fileURL.lastPathComponent, kind: kind.rawValue, contentType: contentType,
            sizeBytes: size, sha256: digest, enqueuedAt: now(), state: .queued, multipart: nil
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

    /// Drops unfinished uploads of one kind, for files where only the newest copy matters,
    /// such as the mesh, which grows with every room.
    func discardUnfinished(scanID: String, kind: UploadKind) async {
        let stale = await ledger.all().filter { $0.scanID == scanID && $0.kind == kind.rawValue && $0.state.isActive }
        guard !stale.isEmpty else { return }
        let ids = Set(stale.map(\.id))
        let running = inFlight.filter { ids.contains($0.key.fileID) }
        for (key, taskID) in running {
            inFlight[key] = nil
            sentBytes[key] = nil
            await session.cancelTask(id: taskID)
        }
        await persist { try await self.ledger.remove(Array(ids)) }
        ids.forEach(storage.removeFiles(for:))
        await emit()
        await abortOnServer(stale)
    }

    /// Best effort: an upload the server never hears about expires on its own.
    private func abortOnServer(_ records: [UploadRecord]) async {
        for record in records {
            guard let uploadID = record.multipart?.uploadID else { continue }
            try? await api.abortUpload(scanID: record.scanID, uploadID: uploadID)
        }
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
        case .succeeded(let etag):
            await markPartUploaded(key, etag: etag ?? "")
            return true
        case .failed(let statusCode, _):
            await recordPartFailure(key, statusCode: statusCode)
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

    private func recordPartFailure(_ key: PartKey, statusCode: Int?) async {
        let limit = configuration.maxPartAttempts
        await persist {
            try await self.ledger.update(key.fileID) { record in
                record.multipart?.updatePart(key.number) { part in
                    part.failureCount += 1
                    if statusCode == 403 { part.expiresAt = .distantPast }
                }
                let attempts = record.multipart?.parts.first { $0.number == key.number }?.failureCount ?? 0
                if attempts >= limit { record.state = .failed(UploadFailure(partStatusCode: statusCode)) }
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
            if record.multipart == nil {
                record = try await beginMultipart(record)
            } else if !reconciled.contains(id) {
                record = try await reconcileWithServer(record)
            }
            guard record.state.isActive, record.multipart != nil else { return }
            try await uploadMissingParts(of: record)
            try await completeIfFinished(id)
        } catch {
            await handleStepFailure(error, id: id)
        }
    }

    private func beginMultipart(_ record: UploadRecord) async throws -> UploadRecord {
        let body = CreateUploadBody(
            kind: record.kind, filename: record.fileName, contentType: record.contentType,
            sizeBytes: record.sizeBytes, partSize: configuration.partSize
        )
        let upload = try await api.createUpload(scanID: record.scanID, body: body, idempotencyKey: record.createKey)
        let expected = PartSlicer.partCount(fileSize: record.sizeBytes, partSize: upload.partSize)
        guard upload.partSize > 0, upload.partCount == expected, expected <= Self.maximumPartCount else {
            throw APIError.malformedResponse
        }
        let multipart = MultipartSession(
            uploadID: upload.id, partSize: upload.partSize, parts: (1...expected).map { UploadPart(number: $0) }
        )
        reconciled.insert(record.id)
        let updated = try await ledger.update(record.id) {
            $0.multipart = multipart
            $0.state = .uploading
        }
        await emit()
        return updated ?? record
    }

    /// Storage is the source of truth for which parts exist. After a relaunch this adopts parts
    /// whose tasks finished while the app was dead and forgets parts storage no longer has.
    private func reconcileWithServer(_ record: UploadRecord) async throws -> UploadRecord {
        guard let multipart = record.multipart else { return record }
        let status = try await api.uploadStatus(scanID: record.scanID, uploadID: multipart.uploadID)
        reconciled.insert(record.id)
        switch status.upload.state {
        case "complete": return try await markCompleted(record.id) ?? record
        case "open": return try await adoptStoredParts(status.uploadedParts, in: record) ?? record
        default: throw APIError.notFound
        }
    }

    private func adoptStoredParts(_ stored: [UploadedPart], in record: UploadRecord) async throws -> UploadRecord? {
        let etags = Dictionary(stored.map { ($0.partNumber, $0.etag) }, uniquingKeysWith: { $1 })
        let updated = try await ledger.update(record.id) { record in
            let numbers = record.multipart?.parts.map(\.number) ?? []
            for number in numbers {
                record.multipart?.updatePart(number) { $0.etag = etags[number] }
            }
        }
        await emit()
        return updated
    }

    private func markCompleted(_ id: UUID) async throws -> UploadRecord? {
        let updated = try await ledger.update(id) { $0.state = .completed }
        storage.removeFiles(for: id)
        transientFailureCount = 0
        await emit()
        return updated
    }

    private func uploadMissingParts(of record: UploadRecord) async throws {
        guard let missing = missingParts(of: record), !missing.isEmpty else { return }
        let freeSlots = max(0, configuration.maxConcurrentParts - inFlight.count)
        let batch = Array(missing.prefix(freeSlots))
        guard !batch.isEmpty else { return }
        for part in try await withFreshURLs(batch, in: record) {
            try await startUpload(of: part, in: record)
        }
    }

    private func missingParts(of record: UploadRecord) -> [UploadPart]? {
        record.multipart?.parts.filter { !$0.isComplete && inFlight[PartKey(fileID: record.id, number: $0.number)] == nil }
    }

    private func withFreshURLs(_ batch: [UploadPart], in record: UploadRecord) async throws -> [UploadPart] {
        let stale = batch.filter { $0.needsFreshURL(at: now(), skew: configuration.urlExpirySkew) }
        guard !stale.isEmpty, let multipart = record.multipart else { return batch }
        let requested = stale.map(\.number)
        let response = try PresignValidation.validate(
            try await api.presignParts(scanID: record.scanID, uploadID: multipart.uploadID, partNumbers: requested),
            requested: requested, policy: configuration.storageHosts
        )
        let expiry = now().addingTimeInterval(TimeInterval(response.expiresInSecs))
        let byNumber = Dictionary(response.parts.map { ($0.partNumber, $0) }, uniquingKeysWith: { $1 })
        let updated = try await ledger.update(record.id) { record in
            for (number, presigned) in byNumber {
                record.multipart?.updatePart(number) {
                    $0.url = presigned.url
                    $0.headers = presigned.headers
                    $0.expiresAt = expiry
                }
            }
        }
        let wanted = Set(batch.map(\.number))
        return updated?.multipart?.parts.filter { wanted.contains($0.number) } ?? batch
    }

    private func startUpload(of part: UploadPart, in record: UploadRecord) async throws {
        guard let partSize = record.multipart?.partSize, let url = part.url else { throw APIError.malformedResponse }
        let key = PartKey(fileID: record.id, number: part.number)
        let partFile = storage.partFileURL(for: record.id, partNumber: part.number)
        _ = try await slicer.slice(
            source: storage.stagedFileURL(for: record.id), partNumber: part.number, partSize: partSize, to: partFile
        )
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        part.headers.forEach { request.setValue($0.value, forHTTPHeaderField: $0.key) }
        inFlight[key] = session.startUpload(request: request, fileURL: partFile, label: key.label)
    }

    private func completeIfFinished(_ id: UUID) async throws {
        guard let record = await ledger.record(id), let multipart = record.multipart, record.state.isActive,
              multipart.parts.allSatisfy(\.isComplete) else { return }
        try await ledger.update(id) { $0.state = .completing }
        _ = try await api.completeUpload(scanID: record.scanID, uploadID: multipart.uploadID, sha256: record.sha256)
        _ = try await markCompleted(id)
    }

    private func handleStepFailure(_ error: Error, id: UUID) async {
        let apiError = (error as? APIError) ?? APIError(transportError: error)
        switch recovery(for: apiError, isStorageError: isStorageError(error)) {
        case .retryLater:
            scheduleRepump()
        case .restartUpload:
            await restartUpload(id)
        case .giveUp:
            await markFailed(id, failure: isStorageError(error) ? .fileUnreadable : UploadFailure(apiError))
        }
    }

    private func isStorageError(_ error: Error) -> Bool {
        !(error is APIError) && !(error is URLError)
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
        reconciled.remove(id)
        await persist {
            try await self.ledger.update(id) {
                $0.multipart = nil
                $0.state = .queued
                $0.restarts = ($0.restarts ?? 0) + 1
            }
        }
        scheduleRepump()
    }

    private func markFailed(_ id: UUID, failure: UploadFailure) async {
        await persist { try await self.ledger.update(id) { $0.state = .failed(failure) } }
        await emit()
    }

    private func resetFailedRecord(_ id: UUID) async {
        reconciled.remove(id)
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
