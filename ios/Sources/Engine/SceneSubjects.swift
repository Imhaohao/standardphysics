import Foundation

/// Names every finding subject in words the owner recognizes, from the engine's scene JSON.
nonisolated enum SceneSubjects {
    static let siteLabel = "Whole space"
    static let routeLabel = "Path through the space"

    struct Scene: Decodable {
        let rooms: [Room]
    }

    struct Room: Decodable {
        let id: String
        let name: String
        let objects: [Item]
        let openings: [Item]
        let walls: [Wall]
    }

    struct Item: Decodable {
        let id: String
        let category: String?
        let kind: String?
    }

    struct Wall: Decodable {
        let id: String
    }

    /// `roomNames` are the owner's names in capture order; they replace the engine's own.
    static func subjects(sceneJSON: String, roomNames: [String]) -> [String: ReportSubject] {
        guard let data = sceneJSON.data(using: .utf8),
              let scene = try? JSONDecoder().decode(Scene.self, from: data)
        else { return [:] }
        var subjects: [String: ReportSubject] = [:]
        for (index, room) in scene.rooms.enumerated() {
            let roomName = roomNames.indices.contains(index) ? roomNames[index] : room.name
            subjects[room.id] = ReportSubject(id: room.id, roomName: roomName, label: roomName)
            for item in room.objects + room.openings {
                subjects[item.id] = ReportSubject(id: item.id, roomName: roomName, label: label(for: item))
            }
            for wall in room.walls {
                subjects[wall.id] = ReportSubject(id: wall.id, roomName: roomName, label: "Wall")
            }
        }
        return subjects
    }

    /// The engine's room names in scene order, for a scan this phone has no manifest for.
    static func roomNames(sceneJSON: String) -> [String] {
        guard let data = sceneJSON.data(using: .utf8),
              let scene = try? JSONDecoder().decode(Scene.self, from: data)
        else { return [] }
        return scene.rooms.map(\.name)
    }

    static func label(for item: Item) -> String {
        let raw = item.category ?? item.kind ?? "Item"
        return raw.replacingOccurrences(of: "_", with: " ").capitalizedFirstLetter
    }

    static func fallback(for subjectID: String, roomID: String?, in subjects: [String: ReportSubject]) -> ReportSubject {
        let roomName = roomID.flatMap { subjects[$0]?.roomName } ?? siteLabel
        let label = subjectID.hasPrefix("route") ? routeLabel : roomName
        return ReportSubject(id: subjectID, roomName: roomName, label: label)
    }
}

private extension String {
    nonisolated var capitalizedFirstLetter: String {
        prefix(1).uppercased() + dropFirst()
    }
}
