import Foundation
import RoomPlan

nonisolated struct ExportedStructure: Sendable, Equatable, Codable {
    let rooms: [Int]
    let usdzFile: String
    let jsonFile: String
}

nonisolated protocol StructureMerging: Sendable {
    /// Writes one USDZ + JSON pair per mergeable group of rooms into `scanDirectory`.
    func export(scanDirectory: URL, roomFiles: [String], frames: [Int]) async throws -> [ExportedStructure]
}

/// `StructureBuilder` only merges rooms that share a world frame (it throws
/// `invalidRoomLocation` otherwise), so rooms from different frames are exported separately.
nonisolated struct StructureMerger: StructureMerging {
    @concurrent
    func export(scanDirectory: URL, roomFiles: [String], frames: [Int]) async throws -> [ExportedStructure] {
        let decoder = JSONDecoder()
        let rooms = try roomFiles.map { try decoder.decode(CapturedRoom.self, from: Data(contentsOf: scanDirectory.appending(path: $0))) }
        let groups = await RoomGrouping.group(frames: frames) { indices in
            try? await StructureBuilder(options: []).capturedStructure(from: indices.map { rooms[$0] })
        }
        var exports: [ExportedStructure] = []
        for (position, group) in groups.enumerated() {
            let name = groups.count == 1 ? "structure" : "structure-\(position)"
            try write(group, rooms: rooms, name: name, into: scanDirectory)
            exports.append(ExportedStructure(rooms: group.rooms, usdzFile: "\(name).usdz", jsonFile: "\(name).json"))
        }
        return exports
    }

    private func write(_ group: RoomGroup<CapturedStructure>, rooms: [CapturedRoom], name: String, into directory: URL) throws {
        let staging = directory.appending(path: ".export-\(UUID().uuidString)", directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: staging, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: staging) }
        let usdz = staging.appending(path: "\(name).usdz")
        let json: Data
        if let structure = group.merged {
            try structure.export(to: usdz)
            json = try JSONEncoder().encode(structure)
        } else {
            let room = rooms[group.rooms[0]]
            try room.export(to: usdz)
            json = try JSONEncoder().encode(room)
        }
        let writer = AtomicFileWriter()
        try writer.write(Data(contentsOf: usdz), to: directory.appending(path: "\(name).usdz"))
        try writer.write(json, to: directory.appending(path: "\(name).json"))
    }
}
