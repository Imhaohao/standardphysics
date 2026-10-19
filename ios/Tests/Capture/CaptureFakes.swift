import ARKit
import Foundation
@testable import StandardPhysics

@MainActor
final class FakeARHost: ARSessionHosting {
    let events: AsyncStream<ARHostEvent>
    private let continuation: AsyncStream<ARHostEvent>.Continuation
    private(set) var runs: [(mode: ARRunMode, worldMap: Data?)] = []
    private(set) var pauses = 0
    var nextCheckpoint: Checkpoint? = Checkpoint(worldMap: Data("map".utf8), snapshotJPEG: Data([0xFF, 0xD8, 0xFF]))
    var parts: [MeshPart] = []
    var runError: (any Error)?

    init() {
        (events, continuation) = AsyncStream.makeStream(of: ARHostEvent.self)
    }

    var arSession: ARSession? { nil }
    var runModes: [ARRunMode] { runs.map(\.mode) }

    func emit(_ event: ARHostEvent) { continuation.yield(event) }

    func run(_ mode: ARRunMode, worldMap: Data?) async throws {
        runs.append((mode, worldMap))
        if let runError { throw runError }
    }

    func pause() { pauses += 1 }
    func checkpoint() async throws -> Checkpoint? { nextCheckpoint }
    func meshParts() -> [MeshPart] { parts }
}

@MainActor
final class FakeRoomScanner: RoomScanning {
    let updates: AsyncStream<RoomScanUpdate>
    private let continuation: AsyncStream<RoomScanUpdate>.Continuation
    private(set) var starts = 0
    private(set) var finishes = 0
    private(set) var cancels = 0
    var roomJSONOnFinish: Data? = Data("{\"walls\":[]}".utf8)

    init() {
        (updates, continuation) = AsyncStream.makeStream(of: RoomScanUpdate.self)
    }

    func emit(_ update: RoomScanUpdate) { continuation.yield(update) }

    func start() { starts += 1 }

    func finish() {
        finishes += 1
        if let roomJSONOnFinish { continuation.yield(.ended(roomJSON: roomJSONOnFinish)) }
    }

    func cancel() { cancels += 1 }
}

final class FakeMerger: StructureMerging, @unchecked Sendable {
    private let lock = NSLock()
    private var calls: [(files: [String], frames: [Int])] = []
    var error: (any Error)?

    var lastCall: (files: [String], frames: [Int])? { lock.withLock { calls.last } }

    func export(scanDirectory: URL, roomFiles: [String], frames: [Int]) async throws -> [ExportedStructure] {
        lock.withLock { calls.append((roomFiles, frames)) }
        if let error { throw error }
        return [ExportedStructure(rooms: Array(roomFiles.indices), usdzFile: "structure.usdz", jsonFile: "structure.json")]
    }
}

@MainActor
final class FakeApplication: CaptureApplication {
    var isIdleTimerDisabled = false
    private(set) var protectedWork = 0
    private(set) var endedWork = 0

    func beginProtectedWork(named name: String) -> BackgroundWorkToken {
        protectedWork += 1
        return BackgroundWorkToken()
    }

    func endProtectedWork(_ token: BackgroundWorkToken) { endedWork += 1 }
}
