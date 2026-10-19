import Foundation

/// Picks the more complete of two captures of the same room, so a room RoomPlan rebuilt after
/// giving up never replaces a fuller one, and the report never counts the room twice.
nonisolated enum RoomSalvage {
    static let surfaceKeys = ["walls", "doors", "windows", "openings", "objects"]

    static func score(_ capturedRoomJSON: Data) -> Int {
        guard let room = try? JSONSerialization.jsonObject(with: capturedRoomJSON) as? [String: Any] else { return 0 }
        return surfaceKeys.reduce(0) { total, key in total + ((room[key] as? [Any])?.count ?? 0) }
    }

    /// A tie goes to `latest`, the capture that ran to the end.
    static func better(_ salvaged: Data?, _ latest: Data) -> Data {
        guard let salvaged, score(salvaged) > score(latest) else { return latest }
        return salvaged
    }
}
