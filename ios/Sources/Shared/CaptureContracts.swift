import Foundation
import CoreVideo
import simd

nonisolated enum PauseReason: String, Codable, Sendable, Equatable {
    case appInactive
    case backgrounded
    case sessionInterrupted
    case trackingLost
    case thermal
    case user
}

nonisolated enum CapturePhase: Codable, Sendable, Equatable {
    case idle
    case scanning(room: Int)
    case paused(room: Int, reason: PauseReason)
    case relocalizing(room: Int)
    case betweenRooms(completed: Int)
    case finishing
    case finished
    case failed(message: String)
}

nonisolated struct RoomRecord: Codable, Sendable, Equatable, Identifiable {
    let index: Int
    var name: String
    let capturedRoomFile: String
    let completedAt: Date

    var id: Int { index }
}

/// Everything on disk for one scan. Written atomically after every change so an app kill
/// at any moment leaves a resumable scan.
nonisolated struct ScanManifest: Codable, Sendable, Equatable {
    static let currentVersion = 1

    var version = ScanManifest.currentVersion
    let scanID: UUID
    var name: String
    let startedAt: Date
    var phase: CapturePhase
    var rooms: [RoomRecord]
    var worldMapFile: String?
    var worldMapSavedAt: Date?
    var relocalizationSnapshotFile: String?
    var meshFile: String?
    var remoteScanID: String?
}

nonisolated enum ElementSource: String, Codable, Sendable {
    case roomplan
    case detector
    case mesh
    case owner
}

nonisolated enum ElementKind: String, Codable, Sendable {
    case wall
    case floor
    case door
    case window
    case opening
    case object
}

/// One thing the app currently understands about the space, in world coordinates.
nonisolated struct LiveElement: Sendable, Identifiable, Equatable {
    let id: String
    let kind: ElementKind
    let category: String
    let transform: simd_float4x4
    let dimensions: SIMD3<Float>
    let confidence: Float
    let source: ElementSource
}

nonisolated enum FindingStatus: String, Codable, Sendable {
    case pass
    case fail
    case needsInfo = "needs_info"
    case notApplicable = "not_applicable"
}

nonisolated enum Jurisdiction: String, Codable, Sendable {
    case ada2010 = "ADA2010"
    case cbc11b = "CBC11B"
}

nonisolated struct MeasuredValue: Codable, Sendable, Equatable {
    let value: Double
    let unit: String
}

nonisolated struct Finding: Codable, Sendable, Equatable, Identifiable {
    let ruleID: String
    let jurisdiction: Jurisdiction
    let section: String
    let subjectID: String
    let status: FindingStatus
    let measured: MeasuredValue?
    let required: String
    let message: String

    var id: String { "\(ruleID)#\(subjectID)" }

    enum CodingKeys: String, CodingKey {
        case ruleID = "rule_id"
        case jurisdiction, section
        case subjectID = "subject_id"
        case status, measured, required, message
    }
}

/// A 2D detection lifted into the world using scene depth.
nonisolated struct Detection: Sendable, Equatable {
    let label: String
    let category: String
    let confidence: Float
    /// Normalized image rect, origin top-left.
    let boundingBox: CGRect
    let worldCenter: SIMD3<Float>?
    let worldSize: SIMD3<Float>?
}

/// The Rust engine behind a protocol so the app runs before the XCFramework lands.
protocol ComplianceEvaluating: Sendable {
    func evaluate(sceneJSON: Data) async throws -> [Finding]
}

protocol ObjectDetecting: Sendable {
    func detect(pixelBuffer: CVPixelBufferWrapper) async throws -> [Detection]
}

/// CVPixelBuffer is not Sendable; ARKit hands buffers off as read-only, so wrapping is safe
/// as long as the detector only reads.
nonisolated struct CVPixelBufferWrapper: @unchecked Sendable {
    let buffer: CVPixelBuffer
}

protocol ScanJournaling: Sendable {
    func create(name: String) async throws -> ScanManifest
    func load(scanID: UUID) async throws -> ScanManifest
    func unfinishedScans() async throws -> [ScanManifest]
    func update(_ manifest: ScanManifest) async throws
    func appendRoom(scanID: UUID, capturedRoomJSON: Data, name: String) async throws -> ScanManifest
    func saveWorldMap(scanID: UUID, data: Data, snapshotJPEG: Data?) async throws -> ScanManifest
    func directory(for scanID: UUID) -> URL
}

/// What the capture screens drive and observe. `CaptureCoordinator` is the real one; previews
/// and tests use a fake.
@MainActor
protocol CaptureControlling: AnyObject, Observable {
    var phase: CapturePhase { get }
    var manifest: ScanManifest? { get }
    /// What RoomPlan and the detector currently see, in world coordinates.
    var liveElements: [LiveElement] { get }
    var detections: [Detection] { get }
    /// On-device findings for finished rooms plus the room in progress.
    var provisionalFindings: [Finding] { get }
    /// One short instruction for the person scanning ("Move closer to the wall").
    var guidance: String? { get }
    /// JPEG of the view at the last checkpoint, shown to line the camera up when resuming.
    var relocalizationSnapshot: Data? { get }

    func startScan(name: String) async
    func resume(scanID: UUID) async
    func pause()
    func continueScanning()
    func finishRoom() async
    func startNextRoom()
    func finishScan() async
    func discardScan() async
}
