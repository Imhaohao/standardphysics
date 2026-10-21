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
    /// Saved before the server is first asked to create the scan, and sent with every attempt,
    /// so a retry after a dropped response or a relaunch never makes a second scan.
    var remoteCreateKey: String?
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
    /// Not a code: something Standard Physics itself could not settle, such as an object it
    /// could not identify. These become questions for the owner, never violations.
    case system = "SYSTEM"
}

nonisolated enum FindingSeverity: String, Codable, Sendable {
    case violation
    case advisory
    case info
}

nonisolated struct MeasuredValue: Codable, Sendable, Equatable {
    let value: Double
    let unit: String
}

/// A measurement that is only known to lie between two values.
nonisolated struct MeasuredRange: Codable, Sendable, Equatable {
    let lo: Double
    let hi: Double
    let unit: String
}

nonisolated enum AskValueType: String, Codable, Sendable {
    case boolean
    case number
    case integer
    case choice = "enum"
    /// A kind of answer this version of the app cannot collect; the question is not shown.
    case unsupported

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = AskValueType(rawValue: raw) ?? .unsupported
    }
}

/// What the owner can tell us to settle a `needs_info` finding, and the metric the answer is
/// stored under. ADA and CBC twins share one ask, so it is asked once per subject and metric.
nonisolated struct FindingAsk: Codable, Sendable, Equatable {
    let metric: String
    let prompt: String
    let valueType: AskValueType
    let unit: String
    let options: [String]
    /// The rule would rather have a photo; an answer from the owner still counts.
    let photo: Bool

    init(metric: String, prompt: String, valueType: AskValueType, unit: String = "", options: [String] = [], photo: Bool = false) {
        self.metric = metric
        self.prompt = prompt
        self.valueType = valueType
        self.unit = unit
        self.options = options
        self.photo = photo
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        metric = try container.decode(String.self, forKey: .metric)
        prompt = try container.decode(String.self, forKey: .prompt)
        valueType = try container.decode(AskValueType.self, forKey: .valueType)
        unit = try container.decodeIfPresent(String.self, forKey: .unit) ?? ""
        options = try container.decodeIfPresent([String].self, forKey: .options) ?? []
        photo = try container.decodeIfPresent(Bool.self, forKey: .photo) ?? false
    }

    enum CodingKeys: String, CodingKey {
        case metric, prompt, unit, options, photo
        case valueType = "value_type"
    }
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
    let title: String?
    let severity: FindingSeverity?
    /// The matching rule in the other jurisdiction, e.g. the CBC rule for an ADA one.
    let counterpartRuleID: String?
    let range: MeasuredRange?
    /// Set when the finding needs an answer only the owner (or a photo) can give.
    let ask: FindingAsk?

    var id: String { "\(ruleID)#\(subjectID)" }
    var isOwnerQuestion: Bool { jurisdiction == .system }

    init(
        ruleID: String, jurisdiction: Jurisdiction, section: String, subjectID: String, status: FindingStatus,
        measured: MeasuredValue?, required: String, message: String, title: String? = nil,
        severity: FindingSeverity? = nil, counterpartRuleID: String? = nil, range: MeasuredRange? = nil,
        ask: FindingAsk? = nil
    ) {
        self.ruleID = ruleID
        self.jurisdiction = jurisdiction
        self.section = section
        self.subjectID = subjectID
        self.status = status
        self.measured = measured
        self.required = required
        self.message = message
        self.title = title
        self.severity = severity
        self.counterpartRuleID = counterpartRuleID
        self.range = range
        self.ask = ask
    }

    /// Reports saved before these fields existed still load, and a severity this version does
    /// not know reads as none rather than failing the whole report.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        ruleID = try container.decode(String.self, forKey: .ruleID)
        jurisdiction = try container.decode(Jurisdiction.self, forKey: .jurisdiction)
        section = try container.decode(String.self, forKey: .section)
        subjectID = try container.decode(String.self, forKey: .subjectID)
        status = try container.decode(FindingStatus.self, forKey: .status)
        measured = try container.decodeIfPresent(MeasuredValue.self, forKey: .measured)
        required = try container.decode(String.self, forKey: .required)
        message = try container.decode(String.self, forKey: .message)
        title = try container.decodeIfPresent(String.self, forKey: .title)
        severity = try? container.decodeIfPresent(FindingSeverity.self, forKey: .severity)
        counterpartRuleID = try container.decodeIfPresent(String.self, forKey: .counterpartRuleID)
        range = try container.decodeIfPresent(MeasuredRange.self, forKey: .range)
        ask = try? container.decodeIfPresent(FindingAsk.self, forKey: .ask)
    }

    enum CodingKeys: String, CodingKey {
        case ruleID = "rule_id"
        case jurisdiction, section
        case subjectID = "subject_id"
        case status, measured, required, message, title, severity, range, ask
        case counterpartRuleID = "counterpart_rule_id"
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
nonisolated protocol ComplianceEvaluating: Sendable {
    func evaluate(sceneJSON: Data) async throws -> [Finding]
}

nonisolated protocol ObjectDetecting: Sendable {
    func detect(pixelBuffer: CVPixelBufferWrapper) async throws -> [Detection]
}

/// CVPixelBuffer is not Sendable; ARKit hands buffers off as read-only, so wrapping is safe
/// as long as the detector only reads.
nonisolated struct CVPixelBufferWrapper: @unchecked Sendable {
    let buffer: CVPixelBuffer
}

nonisolated protocol ScanJournaling: Sendable {
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
    func nameRoom(index: Int, name: String) async
    /// Drops the room in progress (and any relocalization attempt) and scans it from scratch.
    func restartRoom()
    func startNextRoom()
    func finishScan() async
    func discardScan() async
    /// Removes a saved scan and its files, whether or not it is the one currently open.
    func deleteScan(scanID: UUID) async
}
