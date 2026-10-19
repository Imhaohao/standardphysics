import ARKit
import Foundation
import RoomPlan
import Synchronization

nonisolated enum RoomScanUpdate: Sendable, Equatable {
    case elements([LiveElement])
    case instruction(ScanInstruction)
    case ended(roomJSON: Data)
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

    init(continuation: AsyncStream<RoomScanUpdate>.Continuation) {
        self.continuation = continuation
    }

    func cancel() {
        isCancelled.withLock { $0 = true }
    }

    func captureSession(_ session: RoomCaptureSession, didUpdate room: CapturedRoom) {
        publish(.elements(LiveElementMapper.elements(of: room)))
    }

    func captureSession(_ session: RoomCaptureSession, didProvide instruction: RoomCaptureSession.Instruction) {
        publish(.instruction(ScanInstruction(instruction)))
    }

    func captureSession(_ session: RoomCaptureSession, didEndWith data: CapturedRoomData, error: (any Error)?) {
        if let error {
            publish(.failed(message: error.localizedDescription))
            return
        }
        Task { await self.build(data) }
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
