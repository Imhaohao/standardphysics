import Foundation
import os

nonisolated protocol RemoteScanCreating: Sendable {
    func createScan(name: String?, siteName: String?, idempotencyKey: String) async throws -> ScanResponse
}

nonisolated protocol ScanFileUploading: Sendable {
    @discardableResult
    func enqueue(fileURL: URL, scanID: String, kind: UploadKind, contentType: String) async throws -> UUID
    func discardUnfinished(scanID: String, kind: UploadKind) async
}

nonisolated protocol LiveRoomChannel: Sendable {
    var messages: AsyncStream<LiveMessage> { get }
    func open() async
    func sendRoom(_ update: RoomUpdate) async
    var hasUnansweredRooms: Bool { get async }
    func close() async
}

/// Makes sure the server holds every saved room before it is asked to finish the scan.
@MainActor
protocol RoomDelivering: AnyObject {
    func deliverRooms(of manifest: ScanManifest) async throws
}

nonisolated enum ScanStreamingError: Error, Equatable {
    case roomsNotDelivered
}

extension APIClient: RemoteScanCreating {}
extension BackgroundUploader: ScanFileUploading {}
extension LiveChannel: LiveRoomChannel {}

/// Streams a scan to the server while it is captured: creates the remote scan once, sends each
/// finished room over the live channel, queues the room and the latest mesh for upload, and
/// feeds the server's findings back to the capture screen. Signed out, it does nothing.
@MainActor
final class ScanStreamer: CaptureObserving, RoomDelivering {
    struct Dependencies {
        var creator: any RemoteScanCreating
        var uploader: any ScanFileUploading
        var makeChannel: (_ remoteScanID: String) -> any LiveRoomChannel
        var isSignedIn: () -> Bool
        var directory: (_ scanID: UUID) -> URL
        var createAttempts = 3
        var createRetryDelay: Duration = .seconds(2)
        var deliveryTimeout: Duration = .seconds(20)
        var sleep: Sleeper = DefaultSleeper.sleep
    }

    private static let deliveryPollInterval: Duration = .milliseconds(100)

    private struct Session {
        let scanID: UUID
        var remoteScanID: String?
        var channel: (any LiveRoomChannel)?
        var listener: Task<Void, Never>?
    }

    private let dependencies: Dependencies
    private var session: Session?
    private var chain: Task<Void, Never>?
    private let logger = Logger(subsystem: "com.tarunyadgirkar.standardphysics", category: "streaming")

    init(dependencies: Dependencies) {
        self.dependencies = dependencies
    }

    var remoteScanID: String? { session?.remoteScanID }

    func capture(_ link: any CaptureLinking, reached milestone: CaptureMilestone) {
        let previous = chain
        chain = Task { [weak self] in
            await previous?.value
            await self?.handle(milestone, link: link)
        }
    }

    /// Waits for queued milestones to finish, for tests and before finishing a scan.
    func settle() async {
        while let current = chain {
            await current.value
            if chain == current { return }
        }
    }

    // MARK: Milestones

    private func handle(_ milestone: CaptureMilestone, link: any CaptureLinking) async {
        switch milestone {
        case .started(let manifest): await start(manifest, link: link)
        case .resumed(let manifest): await resume(manifest, link: link)
        case .roomSaved(let index, let manifest): await stream(roomIndex: index, of: manifest)
        case .meshSaved(let manifest): await uploadMesh(of: manifest)
        case .discarded(let scanID): if session?.scanID == scanID { await endSession() }
        }
    }

    private func start(_ manifest: ScanManifest, link: any CaptureLinking) async {
        await endSession()
        guard dependencies.isSignedIn() else { return }
        session = Session(scanID: manifest.scanID)
        let key = UUID().uuidString
        await link.recordRemoteCreateKey(key, forScan: manifest.scanID)
        await createRemoteScan(for: manifest, key: key, link: link)
    }

    private func resume(_ manifest: ScanManifest, link: any CaptureLinking) async {
        await endSession()
        guard dependencies.isSignedIn() else { return }
        session = Session(scanID: manifest.scanID, remoteScanID: manifest.remoteScanID)
        if manifest.remoteScanID == nil, let key = manifest.remoteCreateKey {
            await createRemoteScan(for: manifest, key: key, link: link)
        } else if let remoteScanID = manifest.remoteScanID {
            connect(remoteScanID, link: link)
        }
        await resendRooms(of: manifest)
    }

    private func stream(roomIndex: Int, of manifest: ScanManifest) async {
        guard let remoteScanID = activeRemoteID(for: manifest),
              let record = manifest.rooms.first(where: { $0.index == roomIndex }) else { return }
        let url = dependencies.directory(manifest.scanID).appending(path: record.capturedRoomFile)
        await send(roomFile: url, index: roomIndex)
        do {
            try await dependencies.uploader.enqueue(fileURL: url, scanID: remoteScanID, kind: .room, contentType: "application/json")
        } catch {
            logger.error("Room upload could not be queued: \(String(describing: type(of: error)))")
        }
    }

    private func uploadMesh(of manifest: ScanManifest) async {
        guard let remoteScanID = activeRemoteID(for: manifest), let meshFile = manifest.meshFile else { return }
        let url = dependencies.directory(manifest.scanID).appending(path: meshFile)
        await dependencies.uploader.discardUnfinished(scanID: remoteScanID, kind: .mesh)
        do {
            try await dependencies.uploader.enqueue(fileURL: url, scanID: remoteScanID, kind: .mesh, contentType: "application/octet-stream")
        } catch {
            logger.error("Mesh upload could not be queued: \(String(describing: type(of: error)))")
        }
    }

    // MARK: Remote scan

    /// The key makes every attempt safe to repeat; 409 means the first attempt is still running.
    private func createRemoteScan(for manifest: ScanManifest, key: String, link: any CaptureLinking) async {
        for attempt in 1...dependencies.createAttempts {
            do {
                let scan = try await dependencies.creator.createScan(name: manifest.name, siteName: nil, idempotencyKey: key)
                guard session?.scanID == manifest.scanID else { return }
                session?.remoteScanID = scan.id
                await link.recordRemoteScanID(scan.id, forScan: manifest.scanID)
                connect(scan.id, link: link)
                return
            } catch let error as APIError where Self.isWorthRetrying(error) && attempt < dependencies.createAttempts {
                try? await dependencies.sleep(dependencies.createRetryDelay)
            } catch {
                logger.error("Scan was not created on the server: \(String(describing: type(of: error)))")
                return
            }
        }
    }

    private static func isWorthRetrying(_ error: APIError) -> Bool {
        if case .conflict = error { return true }
        return error.isTransient
    }

    private func activeRemoteID(for manifest: ScanManifest) -> String? {
        guard let session, session.scanID == manifest.scanID else { return nil }
        return session.remoteScanID
    }

    // MARK: Live channel

    private func connect(_ remoteScanID: String, link: any CaptureLinking) {
        let channel = dependencies.makeChannel(remoteScanID)
        let messages = channel.messages
        session?.channel = channel
        session?.listener = Task { [weak link] in
            for await message in messages {
                guard let findings = Self.findings(in: message) else { continue }
                link?.mergeServerFindings(findings)
            }
        }
        Task { await channel.open() }
    }

    private nonisolated static func findings(in message: LiveMessage) -> [Finding]? {
        switch message {
        case .findings(let room): room.findings.compactMap(\.asFinding)
        case .hello(let snapshot): snapshot.findings.compactMap(\.asFinding)
        default: nil
        }
    }

    private func send(roomFile url: URL, index: Int) async {
        guard let channel = session?.channel else { return }
        do {
            let data = try Data(contentsOf: url)
            let roomID = RoomIdentity.roomID(capturedRoomJSON: data, fileName: url.lastPathComponent)
            let observations = DetectedObjectFile.objects(forRoomAt: url).compactMap(\.observation)
            await channel.sendRoom(RoomUpdate(
                roomID: roomID, isFinal: true, capturedRoom: try JSONValue(jsonData: data), observations: observations
            ))
        } catch {
            logger.error("Room \(index) could not be read for streaming")
        }
    }

    /// The server merges rooms by id, so sending every saved room again after a relaunch is
    /// harmless and covers rooms the server never answered before the app was killed.
    private func resendRooms(of manifest: ScanManifest) async {
        let directory = dependencies.directory(manifest.scanID)
        for record in manifest.rooms.sorted(by: { $0.index < $1.index }) {
            await send(roomFile: directory.appending(path: record.capturedRoomFile), index: record.index)
        }
    }

    private func endSession() async {
        session?.listener?.cancel()
        await session?.channel?.close()
        session = nil
    }

    // MARK: RoomDelivering

    func deliverRooms(of manifest: ScanManifest) async throws {
        await settle()
        guard let remoteScanID = manifest.remoteScanID else { throw ScanStreamingError.roomsNotDelivered }
        if session?.scanID != manifest.scanID || session?.channel == nil {
            await endSession()
            session = Session(scanID: manifest.scanID, remoteScanID: remoteScanID)
            connectWithoutLink(remoteScanID)
            await resendRooms(of: manifest)
        }
        guard let channel = session?.channel else { throw ScanStreamingError.roomsNotDelivered }
        try await waitForAnswers(on: channel)
    }

    private func connectWithoutLink(_ remoteScanID: String) {
        let channel = dependencies.makeChannel(remoteScanID)
        session?.channel = channel
        Task { await channel.open() }
    }

    private func waitForAnswers(on channel: any LiveRoomChannel) async throws {
        var waited = Duration.zero
        while await channel.hasUnansweredRooms {
            guard waited < dependencies.deliveryTimeout else { throw ScanStreamingError.roomsNotDelivered }
            try await dependencies.sleep(Self.deliveryPollInterval)
            waited += Self.deliveryPollInterval
        }
    }
}
