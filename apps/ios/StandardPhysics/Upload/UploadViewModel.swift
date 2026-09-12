import Foundation

@MainActor
final class UploadViewModel: ObservableObject {
    @Published private(set) var state: ScanState = .uploading
    @Published private(set) var uploadedCount = 0
    @Published private(set) var totalCount = 0
    @Published private(set) var scanID: String?
    @Published private(set) var errorMessage: String?

    private let scan: CapturedScan
    private let name: String
    private let client: ScanUploadClient
    private var uploadStore: ResumableUploadStore
    private var task: Task<Void, Never>?

    init(scan: CapturedScan, name: String, client: ScanUploadClient) {
        self.scan = scan
        self.name = name
        self.client = client
        uploadStore = ResumableUploadStore(captureDirectory: scan.directory)
        scanID = uploadStore.scanID
        uploadedCount = uploadStore.completedArtifactIDs.count
        totalCount = scan.artifacts.count
    }

    func start() {
        guard task == nil else { return }
        task = Task { [weak self] in await self?.run() }
    }

    func retry() {
        errorMessage = nil
        state = .uploading
        task = nil
        start()
    }

    func cancel() {
        task?.cancel()
        task = nil
    }

    private func run() async {
        do {
            let remoteID = try await prepareRemoteScan()
            scanID = remoteID
            try await uploadArtifacts(to: remoteID)
            let remote = uploadStore.isFinalized
                ? try await client.scan(id: remoteID)
                : try await finalize(remoteID)
            state = remote.state
            try await pollUntilFinished(remoteID)
        } catch is CancellationError {
            return
        } catch {
            errorMessage = "Keep this scan and try the upload again."
            task = nil
        }
    }

    private func prepareRemoteScan() async throws -> String {
        if let existing = uploadStore.scanID { return existing }
        let remote = try await client.createScan(name: name, duration: scan.duration)
        try uploadStore.begin(scanID: remote.id)
        return remote.id
    }

    private func uploadArtifacts(to scanID: String) async throws {
        for artifact in scan.artifacts where uploadStore.needsUpload(artifactID: artifact.id) {
            try Task.checkCancellation()
            try await client.upload(artifact, to: scanID)
            try uploadStore.recordUploaded(artifactID: artifact.id)
            uploadedCount = uploadStore.completedArtifactIDs.count
        }
    }

    private func finalize(_ scanID: String) async throws -> RemoteScan {
        let remote = try await client.complete(scanID: scanID)
        try uploadStore.recordFinalized()
        return remote
    }

    private func pollUntilFinished(_ scanID: String) async throws {
        while state != .ready && state != .failed {
            try await Task.sleep(for: .seconds(2))
            state = try await client.scan(id: scanID).state
        }
        if state == .failed {
            errorMessage = "Open the saved scan and try again."
        }
        task = nil
    }
}
