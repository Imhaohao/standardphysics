import ARKit
import Foundation
import RoomPlan
import Synchronization

nonisolated enum RoomScanUpdate: Sendable, Equatable {
    case elements([LiveElement])
    case instruction(ScanInstruction)
    case ended(roomJSON: Data)
    /// What RoomPlan had when it gave up, sent just before `.failed`.
    case salvaged(roomJSON: Data)
    case failed(message: String)
}

protocol RoomScanning: AnyObject {
    var updates: AsyncStream<RoomScanUpdate> { get }
    func start()
    /// Stops capture while leaving the AR session running; the built room arrives as `.ended`.
    func finish()
    /// Drops the room in progress; nothing more is published for it.
    func cancel()
}

/// One `RoomCaptureSession` per room, all sharing the host's `ARSession` so rooms share a frame.
final class RoomScanner: RoomScanning {
    let updates: AsyncStream<RoomScanUpdate>

    private let continuation: AsyncStream<RoomScanUpdate>.Continuation
    private let arSession: ARSession
    private var captureSession: RoomCaptureSession?
    private var relay: RoomCaptureRelay?

    init(arSession: ARSession) {
        self.arSession = arSession
        (updates, continuation) = AsyncStream.makeStream(of: RoomScanUpdate.self, bufferingPolicy: .bufferingNewest(16))
    }

    func start() {
        cancel()
        let relay = RoomCaptureRelay(continuation: continuation)
        let session = RoomCaptureSession(arSession: arSession)
        session.delegate = relay
        var configuration = RoomCaptureSession.Configuration()
        configuration.isCoachingEnabled = true
        session.run(configuration: configuration)
        self.relay = relay
        captureSession = session
    }

    func finish() {
        captureSession?.stop(pauseARSession: false)
        captureSession = nil
    }

    func cancel() {
        relay?.cancel()
        captureSession?.stop(pauseARSession: false)
        captureSession = nil
        relay = nil
    }
}

nonisolated final class RoomCaptureRelay: RoomCaptureSessionDelegate, Sendable {
    private let continuation: AsyncStream<RoomScanUpdate>.Continuation
    private let isCancelled = Mutex(false)
    private let latestRoom = Mutex<CapturedRoom?>(nil)

    init(continuation: AsyncStream<RoomScanUpdate>.Continuation) {
        self.continuation = continuation
    }

    func cancel() {
        isCancelled.withLock { $0 = true }
    }

    func captureSession(_ session: RoomCaptureSession, didUpdate room: CapturedRoom) {
        latestRoom.withLock { $0 = room }
        publish(.elements(LiveElementMapper.elements(of: room)))
    }

    func captureSession(_ session: RoomCaptureSession, didProvide instruction: RoomCaptureSession.Instruction) {
        publish(.instruction(ScanInstruction(instruction)))
    }

    func captureSession(_ session: RoomCaptureSession, didEndWith data: CapturedRoomData, error: (any Error)?) {
        if let error {
            let message = error.localizedDescription
            Task { await self.salvage(data, thenFail: message) }
            return
        }
        Task { await self.build(data) }
    }

    /// RoomPlan often gives up after an interruption; whatever it had built is still worth keeping.
    private func salvage(_ data: CapturedRoomData, thenFail message: String) async {
        let lastLive = latestRoom.withLock { $0 }
        if let json = await Self.salvagedJSON(from: data, lastLive: lastLive) {
            publish(.salvaged(roomJSON: json))
        }
        publish(.failed(message: message))
    }

    private static func salvagedJSON(from data: CapturedRoomData, lastLive: CapturedRoom?) async -> Data? {
        if let built = try? await roomJSON(from: data) { return built }
        return lastLive.flatMap { try? JSONEncoder().encode($0) }
    }

    private func build(_ data: CapturedRoomData) async {
        do {
            publish(.ended(roomJSON: try await Self.roomJSON(from: data)))
        } catch {
            publish(.failed(message: error.localizedDescription))
        }
    }

    /// No `beautifyObjects`: compliance needs measured positions, not tidied ones.
    @concurrent
    private static func roomJSON(from data: CapturedRoomData) async throws -> Data {
        let room = try await RoomBuilder(options: []).capturedRoom(from: data)
        return try JSONEncoder().encode(room)
    }

    private func publish(_ update: RoomScanUpdate) {
        guard !isCancelled.withLock({ $0 }) else { return }
        continuation.yield(update)
    }
}
