import Foundation

@MainActor
final class UploadViewModel: ObservableObject {
    @Published private(set) var state: ScanState = .uploading
    @Published private(set) var uploadedCount = 0
    @Published private(set) var totalCount = 0
    @Published private(set) var scanID: UUID?
    @Published private(set) var errorMessage: String?
    @Published private(set) var optionalUploadErrorMessage: String?
    @Published private(set) var pendingOptionalUploadCount = 0

    private static let coreArtifactKinds: [ArtifactKind] = [
        .roomUSDZ,
        .roomJSON,
        .roomMetadata,
        .poses,
        .coverage
    ]

    private let scan: CapturedScan
    private let name: String
    private let client: ScanUploadClient
    private let pollInterval: Duration
    private var uploadStore: ResumableUploadStore
    private var task: Task<Void, Never>?
    private var activeRunID: UUID?

    private enum RunMode {
        case full(replacingFailedRemote: Bool)
        case optionalOnly
    }

    init(
        scan: CapturedScan,
        name: String,
        client: ScanUploadClient,
        pollInterval: Duration = .seconds(2)
    ) {
        self.scan = scan
        self.name = name
        self.client = client
        self.pollInterval = pollInterval
        uploadStore = ResumableUploadStore(captureDirectory: scan.directory)
        scanID = uploadStore.scanID
        uploadedCount = uploadStore.completedArtifactIDs.count
        totalCount = scan.artifacts.count
        pendingOptionalUploadCount = scan.artifacts.filter {
            !Self.coreArtifactKinds.contains($0.kind)
                && uploadStore.needsUpload(artifactID: $0.id)
        }.count
        state = uploadStore.lastServerState ?? .uploading
        if state == .failed {
            errorMessage = "Open the saved scan and try again."
        }
    }

    func start() {
        guard task == nil, state != .failed else { return }
        beginRun(mode: .full(replacingFailedRemote: false))
    }

    func retry() {
        if state == .ready, pendingOptionalUploadCount > 0 {
            cancel()
            optionalUploadErrorMessage = nil
            beginRun(mode: .optionalOnly)
            return
        }

        let replacingFailedRemote = state == .failed || uploadStore.lastServerState == .failed
        cancel()
        errorMessage = nil
        optionalUploadErrorMessage = nil
        state = .uploading
        beginRun(mode: .full(replacingFailedRemote: replacingFailedRemote))
    }

    func cancel() {
        activeRunID = nil
        task?.cancel()
        task = nil
    }

    private func beginRun(mode: RunMode) {
        let runID = UUID()
        activeRunID = runID
        task = Task { [weak self] in
            await self?.run(runID: runID, mode: mode)
        }
    }

    private func run(runID: UUID, mode: RunMode) async {
        do {
            if case .optionalOnly = mode {
                let remoteID = try existingScanID()
                try await uploadOptionalArtifacts(to: remoteID, runID: runID)
                finish(runID)
                return
            }

            guard case let .full(replacingFailedRemote) = mode else { return }
            let remoteID = try await prepareRemoteScan(
                runID: runID,
                replacingFailedRemote: replacingFailedRemote
            )
            try requireActive(runID)
            scanID = remoteID

            try await uploadCoreArtifacts(to: remoteID, runID: runID)
            let remote = try await finalizedRemoteScan(id: remoteID, runID: runID)
            try record(remote.state, runID: runID)
            if state == .failed {
                errorMessage = "Open the saved scan and try again."
                finish(runID)
                return
            }

            async let optionalUploads: Void = uploadOptionalArtifactsReportingFailure(
                to: remoteID,
                runID: runID
            )
            try await pollUntilFinished(remoteID, runID: runID)
            await optionalUploads
            finish(runID)
        } catch is CancellationError {
            return
        } catch UploadStoreError.apiBaseURLMismatch {
            guard isActive(runID) else { return }
            errorMessage = "This scan is linked to a different upload server."
            finish(runID)
        } catch {
            guard isActive(runID) else { return }
            if state != .ready {
                errorMessage = "Keep this scan and try the upload again."
            }
            finish(runID)
        }
    }

    private func prepareRemoteScan(runID: UUID, replacingFailedRemote: Bool) async throws -> UUID {
        if !replacingFailedRemote, let existing = uploadStore.scanID {
            try uploadStore.bindOrValidate(apiBaseURL: client.baseURL)
            return existing
        }

        let remote = try await client.createScan(name: name, duration: scan.duration)
        try requireActive(runID)
        if uploadStore.scanID == nil {
            try uploadStore.begin(scanID: remote.id, apiBaseURL: client.baseURL)
        } else {
            try uploadStore.replaceRemoteScan(with: remote.id, apiBaseURL: client.baseURL)
            uploadedCount = uploadStore.completedArtifactIDs.count
            refreshPendingOptionalUploadCount()
        }
        return remote.id
    }

    private func uploadCoreArtifacts(to scanID: UUID, runID: UUID) async throws {
        try await uploadArtifacts(coreArtifacts(), to: scanID, runID: runID)
    }

    private func uploadOptionalArtifacts(to scanID: UUID, runID: UUID) async throws {
        try await uploadArtifacts(optionalArtifacts(), to: scanID, runID: runID)
    }

    private func uploadOptionalArtifactsReportingFailure(to scanID: UUID, runID: UUID) async {
        do {
            try await uploadOptionalArtifacts(to: scanID, runID: runID)
        } catch is CancellationError {
            return
        } catch {
            guard isActive(runID) else { return }
            optionalUploadErrorMessage = "Some additional scan evidence could not upload."
        }
    }

    private func uploadArtifacts(
        _ artifacts: [CaptureArtifact],
        to scanID: UUID,
        runID: UUID
    ) async throws {
        for artifact in artifacts where uploadStore.needsUpload(artifactID: artifact.id) {
            try requireActive(runID)
            try await client.upload(artifact, to: scanID)
            try requireActive(runID)
            try uploadStore.recordUploaded(artifactID: artifact.id)
            uploadedCount = uploadStore.completedArtifactIDs.count
            refreshPendingOptionalUploadCount()
        }
    }

    private func finalizedRemoteScan(id scanID: UUID, runID: UUID) async throws -> RemoteScan {
        if uploadStore.isFinalized {
            let remote = try await client.scan(id: scanID)
            try requireActive(runID)
            return remote
        }

        let remote = try await client.complete(scanID: scanID)
        try requireActive(runID)
        try uploadStore.recordFinalized()
        return remote
    }

    private func pollUntilFinished(_ scanID: UUID, runID: UUID) async throws {
        while state != .ready && state != .failed {
            try await Task.sleep(for: pollInterval)
            try requireActive(runID)
            let remote = try await client.scan(id: scanID)
            try requireActive(runID)
            try record(remote.state, runID: runID)
        }
        if state == .failed {
            errorMessage = "Open the saved scan and try again."
        }
    }

    private func record(_ serverState: ScanState, runID: UUID) throws {
        try requireActive(runID)
        try uploadStore.record(state: serverState)
        state = serverState
    }

    private func coreArtifacts() throws -> [CaptureArtifact] {
        try Self.coreArtifactKinds.map { kind in
            guard let artifact = scan.artifacts.first(where: { $0.kind == kind }) else {
                throw UploadViewModelError.missingCoreArtifact(kind)
            }
            return artifact
        }
    }

    private func optionalArtifacts() -> [CaptureArtifact] {
        scan.artifacts.filter { artifact in
            !Self.coreArtifactKinds.contains(artifact.kind)
        }
    }

    private func refreshPendingOptionalUploadCount() {
        pendingOptionalUploadCount = optionalArtifacts().filter {
            uploadStore.needsUpload(artifactID: $0.id)
        }.count
    }

    private func existingScanID() throws -> UUID {
        guard let scanID = uploadStore.scanID else { throw UploadStoreError.scanNotStarted }
        return scanID
    }

    private func requireActive(_ runID: UUID) throws {
        try Task.checkCancellation()
        guard isActive(runID) else { throw CancellationError() }
    }

    private func isActive(_ runID: UUID) -> Bool {
        activeRunID == runID
    }

    private func finish(_ runID: UUID) {
        guard isActive(runID) else { return }
        activeRunID = nil
        task = nil
    }
}

enum UploadViewModelError: Error {
    case missingCoreArtifact(ArtifactKind)
}
