import Foundation

/// `rooms/<n>.relabel.json`: the crops saved for a room's doubtful RoomPlan objects, and the
/// server artifact each one became once uploaded.
nonisolated struct RelabelCropFile: Codable, Sendable, Equatable {
    static let currentVersion = 1

    struct Entry: Codable, Sendable, Equatable {
        let objectID: String
        /// Next to the room file, e.g. `0.relabel-3.jpg`.
        let cropFile: String
        var artifactID: String?

        enum CodingKeys: String, CodingKey {
            case objectID = "object_id"
            case cropFile = "crop_file"
            case artifactID = "artifact_id"
        }
    }

    var version = currentVersion
    var entries: [Entry]

    /// `rooms/0.json` keeps its relabel crops in `rooms/0.relabel.json`.
    static func path(forRoomFile roomFile: String) -> String {
        "\((roomFile as NSString).deletingPathExtension).relabel.json"
    }

    /// `rooms/0.json`'s third crop is `rooms/0.relabel-2.jpg`.
    static func cropPath(forRoomFile roomFile: String, index: Int) -> String {
        "\((roomFile as NSString).deletingPathExtension).relabel-\(index).jpg"
    }

    static func url(forRoomAt roomURL: URL) -> URL {
        roomURL.deletingLastPathComponent().appending(path: path(forRoomFile: roomURL.lastPathComponent))
    }

    static func cropURL(of entry: Entry, forRoomAt roomURL: URL) -> URL {
        roomURL.deletingLastPathComponent().appending(path: entry.cropFile)
    }

    /// No file, or one this build cannot read, means the room has no crops.
    static func load(forRoomAt roomURL: URL) -> RelabelCropFile? {
        guard let data = try? Data(contentsOf: url(forRoomAt: roomURL)),
              let file = try? JSONDecoder().decode(RelabelCropFile.self, from: data),
              file.version <= currentVersion
        else { return nil }
        return file
    }

    func encoded() throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return try encoder.encode(self)
    }

    /// What the server needs to check each uploaded crop's object.
    var observations: [JSONValue] {
        entries.compactMap { entry in
            guard let artifactID = entry.artifactID else { return nil }
            return .object([
                "id": .string("relabel-\(entry.objectID)"),
                "relabel_object_id": .string(entry.objectID),
                "crop_artifact_id": .string(artifactID),
            ])
        }
    }

    var pendingUploads: [Entry] {
        entries.filter { $0.artifactID == nil }
    }

    mutating func record(artifactIDs: [String: String]) {
        for index in entries.indices {
            if let artifactID = artifactIDs[entries[index].objectID] {
                entries[index].artifactID = artifactID
            }
        }
    }
}
