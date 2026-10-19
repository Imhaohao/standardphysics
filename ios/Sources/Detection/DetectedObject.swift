import Foundation
import simd

nonisolated struct ScenePoint: Codable, Sendable, Equatable {
    let x: Double
    let y: Double
    let z: Double
}

/// A detector object in the engine's frame: metres, Y up, `center.y` and `topHeight` above the
/// room's floor, X and Z as RoomPlan has them. Encodes as the server's detector observation.
nonisolated struct DetectedObject: Codable, Sendable, Equatable {
    let id: String
    let category: String
    let label: String
    let center: ScenePoint
    /// Width along world X, height, depth along world Z (the box is not rotated, `yaw` is 0).
    let size: ScenePoint
    let yaw: Double
    let topHeight: Double
    let confidence: Double
    let hits: Int

    enum CodingKeys: String, CodingKey {
        case id, category, label, center, size, yaw, confidence, hits
        case topHeight = "top_height"
    }

    init(id: String, category: String, label: String, center: ScenePoint, size: ScenePoint, confidence: Double, hits: Int) {
        self.id = id
        self.category = category
        self.label = label
        self.center = center
        self.size = size
        yaw = 0
        topHeight = center.y + size.y / 2
        self.confidence = confidence
        self.hits = hits
    }

    init(track: DetectionTrack, floorLevel: Float, id: String) {
        let center = SIMD3<Double>(track.center) - SIMD3(0, Double(floorLevel), 0)
        self.init(
            id: id,
            category: track.category,
            label: track.label,
            center: ScenePoint(x: center.x, y: center.y, z: center.z),
            size: ScenePoint(x: Double(track.size.x), y: Double(track.size.y), z: Double(track.size.z)),
            confidence: Double(track.meanConfidence),
            hits: track.hits
        )
    }

    var observation: JSONValue? {
        (try? JSONEncoder().encode(self)).flatMap { try? JSONValue(jsonData: $0) }
    }
}

/// What a finished room keeps from the detector: confirmed tracks RoomPlan did not already report.
nonisolated enum DetectedObjects {
    /// Plan IoU at or above this with a compatible RoomPlan object means RoomPlan already has it.
    static let duplicateIoU: Float = 0.25
    /// Slack around a RoomPlan footprint when asking whether a detection's center falls inside it.
    static let footprintMargin: Float = 0.1

    /// Categories that name the same physical thing whichever model saw it.
    static let compatibleGroups: [Set<String>] = [
        ["table", "dining_table"],
        ["sofa", "chair", "bench"],
        ["oven", "stove"],
    ]

    static func finished(
        tracks: [DetectionTrack], room: CapturedRoomGeometry, makeID: () -> String = { "detector-\(UUID().uuidString)" }
    ) -> (objects: [DetectedObject], kept: [DetectionTrack]) {
        let kept = tracks.filter { !isAlreadyPlanned($0, in: room) }
        let objects = kept.map { DetectedObject(track: $0, floorLevel: room.floorLevel, id: makeID()) }
        return (objects, kept)
    }

    static func isAlreadyPlanned(_ track: DetectionTrack, in room: CapturedRoomGeometry) -> Bool {
        room.objects.contains { planned in
            areCompatible(track.category, planned.category)
                && (isCenter(track.center, inside: planned) || planIoU(track, planned) >= duplicateIoU)
        }
    }

    static func areCompatible(_ detected: String, _ planned: String) -> Bool {
        detected == planned || compatibleGroups.contains { $0.contains(detected) && $0.contains(planned) }
    }

    static func isCenter(_ center: SIMD3<Float>, inside planned: CapturedRoomGeometry.PlannedObject) -> Bool {
        let local = planned.transform.inverse * SIMD4(center, 1)
        let half = planned.dimensions / 2 + footprintMargin
        return abs(local.x) <= half.x && abs(local.z) <= half.z
    }

    static func planIoU(_ track: DetectionTrack, _ planned: CapturedRoomGeometry.PlannedObject) -> Float {
        let detected = PlanRect(center: SIMD2(track.center.x, track.center.z), halfExtent: SIMD2(track.size.x, track.size.z) / 2)
        let intersection = detected.intersectionArea(with: PlanRect(enclosing: planned))
        let union = detected.area + PlanRect(enclosing: planned).area - intersection
        return union > 0 ? intersection / union : 0
    }
}

/// An axis-aligned rectangle in plan (world X, world Z).
private nonisolated struct PlanRect {
    let minimum: SIMD2<Float>
    let maximum: SIMD2<Float>

    init(center: SIMD2<Float>, halfExtent: SIMD2<Float>) {
        minimum = center - halfExtent
        maximum = center + halfExtent
    }

    /// The axis-aligned bounds of a RoomPlan object's rotated footprint.
    init(enclosing planned: CapturedRoomGeometry.PlannedObject) {
        let half = planned.dimensions / 2
        let corners = [SIMD2<Float>(-1, -1), SIMD2(1, -1), SIMD2(1, 1), SIMD2(-1, 1)].map { sign in
            let world = planned.transform * SIMD4(sign.x * half.x, 0, sign.y * half.z, 1)
            return SIMD2(world.x, world.z)
        }
        minimum = corners.reduce(corners[0]) { simd_min($0, $1) }
        maximum = corners.reduce(corners[0]) { simd_max($0, $1) }
    }

    var area: Float {
        let extent = simd_max(maximum - minimum, .zero)
        return extent.x * extent.y
    }

    func intersectionArea(with other: PlanRect) -> Float {
        let extent = simd_max(simd_min(maximum, other.maximum) - simd_max(minimum, other.minimum), .zero)
        return extent.x * extent.y
    }
}

/// `rooms/<n>.detections.json`, written next to the room it belongs to.
nonisolated struct DetectedObjectFile: Codable, Sendable, Equatable {
    static let currentVersion = 1

    var version = currentVersion
    let objects: [DetectedObject]

    /// `rooms/0.json` keeps its detector objects in `rooms/0.detections.json`.
    static func path(forRoomFile roomFile: String) -> String {
        let stem = (roomFile as NSString).deletingPathExtension
        return "\(stem).detections.json"
    }

    /// No file, or one this build cannot read, means the room has no detector objects.
    static func objects(forRoomAt roomURL: URL) -> [DetectedObject] {
        let url = roomURL.deletingLastPathComponent().appending(path: path(forRoomFile: roomURL.lastPathComponent))
        guard let data = try? Data(contentsOf: url),
              let file = try? JSONDecoder().decode(DetectedObjectFile.self, from: data),
              file.version <= currentVersion
        else { return [] }
        return file.objects
    }
}
