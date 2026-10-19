import Foundation

/// Which AR coordinate frame each room was captured in. A frame starts with every `.fresh`
/// session run; relocalizing onto the saved world map rejoins that map's frame.
nonisolated struct FrameLog: Codable, Sendable, Equatable {
    var current = 0
    var worldMapFrame: Int?
    var roomFrames: [Int] = []

    mutating func beginNewFrame() {
        current = (roomFrames + [current, worldMapFrame ?? 0]).max().map { $0 + 1 } ?? 0
    }

    mutating func rejoinWorldMapFrame() {
        current = worldMapFrame ?? current
    }

    mutating func recordRoom(_ index: Int) {
        let padded = roomFrames + Array(repeating: current, count: max(0, index + 1 - roomFrames.count))
        roomFrames = Array(padded.prefix(index)) + [current] + Array(padded.dropFirst(index + 1))
    }

    func frame(ofRoom index: Int) -> Int {
        index < roomFrames.count ? roomFrames[index] : 0
    }
}

nonisolated struct RoomGroup<Merged: Sendable>: Sendable {
    let rooms: [Int]
    /// `nil` for a single room, which is exported on its own.
    let merged: Merged?
}

/// Rooms only merge when they share a coordinate frame. Within a frame, rooms are added one at a
/// time and a room that makes the merge fail starts a new group instead of sinking the export.
nonisolated enum RoomGrouping {
    static func group<Merged: Sendable>(
        frames: [Int],
        merge: ([Int]) async -> Merged?
    ) async -> [RoomGroup<Merged>] {
        var groups: [RoomGroup<Merged>] = []
        for rooms in roomsByFrame(frames) {
            groups += await groupWithinFrame(rooms, merge: merge)
        }
        return groups
    }

    static func roomsByFrame(_ frames: [Int]) -> [[Int]] {
        var order: [Int] = []
        var rooms: [Int: [Int]] = [:]
        for (room, frame) in frames.enumerated() {
            if rooms[frame] == nil { order.append(frame) }
            rooms[frame, default: []].append(room)
        }
        return order.compactMap { rooms[$0] }
    }

    private static func groupWithinFrame<Merged: Sendable>(
        _ rooms: [Int],
        merge: ([Int]) async -> Merged?
    ) async -> [RoomGroup<Merged>] {
        guard rooms.count > 1 else { return rooms.map { RoomGroup(rooms: [$0], merged: nil) } }
        if let merged = await merge(rooms) { return [RoomGroup(rooms: rooms, merged: merged)] }
        var groups: [RoomGroup<Merged>] = []
        var current = RoomGroup<Merged>(rooms: [rooms[0]], merged: nil)
        for room in rooms.dropFirst() {
            let candidate = current.rooms + [room]
            if let merged = await merge(candidate) {
                current = RoomGroup(rooms: candidate, merged: merged)
            } else {
                groups.append(current)
                current = RoomGroup(rooms: [room], merged: nil)
            }
        }
        return groups + [current]
    }
}
