import Foundation

struct ResumableUploadStore {
    private struct State: Codable {
        var scanID: String?
        var completedArtifactIDs: Set<String> = []
    }

    private let stateURL: URL
    private var state: State

    var scanID: String? { state.scanID }
    var completedArtifactIDs: Set<String> { state.completedArtifactIDs }

    init(captureDirectory: URL) {
        stateURL = captureDirectory.appendingPathComponent("upload-state.json")
        state = (try? Data(contentsOf: stateURL))
            .flatMap { try? JSONDecoder().decode(State.self, from: $0) }
            ?? State()
    }

    func needsUpload(artifactID: String) -> Bool {
        !state.completedArtifactIDs.contains(artifactID)
    }

    mutating func begin(scanID: String) throws {
        guard state.scanID == nil || state.scanID == scanID else {
            throw UploadStoreError.scanAlreadyStarted
        }
        state.scanID = scanID
        try persist()
    }

    mutating func recordUploaded(artifactID: String) throws {
        guard state.scanID != nil else { throw UploadStoreError.scanNotStarted }
        state.completedArtifactIDs.insert(artifactID)
        try persist()
    }

    private func persist() throws {
        let data = try JSONEncoder().encode(state)
        try data.write(to: stateURL, options: .atomic)
    }
}

enum UploadStoreError: Error {
    case scanAlreadyStarted
    case scanNotStarted
}
