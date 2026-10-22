import Foundation
import simd

/// The parts of a CapturedRoom JSON that place detector objects: where the floor is and what
/// RoomPlan already found. Mirrors `sp-core` `roomplan::convert` so both agree on the floor.
nonisolated struct CapturedRoomGeometry: Sendable, Equatable {
    struct PlannedObject: Sendable, Equatable {
        /// sp-core's category id: the RoomPlan case in snake_case (`washerDryer` is `washer_dryer`).
        let category: String
        let transform: simd_float4x4
        let dimensions: SIMD3<Float>
        /// RoomPlan's identifier as the JSON spells it, which is also the sp-core object id.
        var identifier: String = ""
    }

    /// World Y of the floor: the lowest captured floor, else the lowest wall bottom, else the lowest object bottom.
    let floorLevel: Float
    let objects: [PlannedObject]

    init(floorLevel: Float, objects: [PlannedObject]) {
        self.floorLevel = floorLevel
        self.objects = objects
    }

    init?(capturedRoomJSON: Data) {
        guard let room = try? JSONDecoder().decode(RawRoom.self, from: capturedRoomJSON) else { return nil }
        objects = room.objects.compactMap(\.planned)
        floorLevel = Self.floorLevel(of: room)
    }

    private static func floorLevel(of room: RawRoom) -> Float {
        let floors = room.floors.compactMap { $0.translation?.y }
        let walls = room.walls.compactMap(\.bottom)
        let objects = room.objects.compactMap(\.bottom)
        return [floors, walls, objects].first { !$0.isEmpty }?.min() ?? 0
    }

    static func snakeCase(_ camel: String) -> String {
        camel.reduce(into: "") { result, character in
            if character.isUppercase, !result.isEmpty { result.append("_") }
            result.append(character.lowercased())
        }
    }
}

private nonisolated struct RawRoom: Decodable {
    var floors: [RawSurface] = []
    var walls: [RawSurface] = []
    var objects: [RawSurface] = []

    enum CodingKeys: String, CodingKey {
        case floors, walls, objects
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        floors = try container.decodeIfPresent([RawSurface].self, forKey: .floors) ?? []
        walls = try container.decodeIfPresent([RawSurface].self, forKey: .walls) ?? []
        objects = try container.decodeIfPresent([RawSurface].self, forKey: .objects) ?? []
    }
}

private nonisolated struct RawSurface: Decodable {
    let identifier: String?
    let category: [String: EmptyValue]?
    let dimensions: [Float]?
    let transform: [Float]?

    var matrix: simd_float4x4? {
        guard let transform, transform.count == 16 else { return nil }
        let column = { (index: Int) in SIMD4(transform[index * 4], transform[index * 4 + 1], transform[index * 4 + 2], transform[index * 4 + 3]) }
        return simd_float4x4(column(0), column(1), column(2), column(3))
    }

    var size: SIMD3<Float>? {
        guard let dimensions, dimensions.count == 3 else { return nil }
        return SIMD3(dimensions[0], dimensions[1], dimensions[2])
    }

    var translation: SIMD3<Float>? {
        matrix.map { SIMD3($0.columns.3.x, $0.columns.3.y, $0.columns.3.z) }
    }

    var bottom: Float? {
        guard let translation, let size else { return nil }
        return translation.y - size.y / 2
    }

    var planned: CapturedRoomGeometry.PlannedObject? {
        guard let matrix, let size, let roomPlanCase = category?.keys.first else { return nil }
        return CapturedRoomGeometry.PlannedObject(
            category: CapturedRoomGeometry.snakeCase(roomPlanCase), transform: matrix, dimensions: size,
            identifier: identifier ?? ""
        )
    }
}

private nonisolated struct EmptyValue: Decodable {
    init(from decoder: Decoder) throws {}
}
