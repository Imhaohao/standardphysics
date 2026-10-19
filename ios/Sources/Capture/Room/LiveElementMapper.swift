import Foundation
import RoomPlan

nonisolated enum LiveElementMapper {
    static func elements(of room: CapturedRoom) -> [LiveElement] {
        let surfaces = room.floors + room.walls + room.openings + room.windows + room.doors
        return surfaces.map(element(of:)) + room.objects.map(element(of:))
    }

    static func element(of surface: CapturedRoom.Surface) -> LiveElement {
        let (kind, category) = describe(surface.category)
        return LiveElement(
            id: surface.identifier.uuidString,
            kind: kind,
            category: category,
            transform: surface.transform,
            dimensions: surface.dimensions,
            confidence: confidence(surface.confidence),
            source: .roomplan
        )
    }

    static func element(of object: CapturedRoom.Object) -> LiveElement {
        LiveElement(
            id: object.identifier.uuidString,
            kind: .object,
            category: categoryName(object.category),
            transform: object.transform,
            dimensions: object.dimensions,
            confidence: confidence(object.confidence),
            source: .roomplan
        )
    }

    static func describe(_ category: CapturedRoom.Surface.Category) -> (ElementKind, String) {
        switch category {
        case .wall: (.wall, "wall")
        case .floor: (.floor, "floor")
        case .door(let isOpen): (.door, isOpen ? "door_open" : "door")
        case .window: (.window, "window")
        case .opening: (.opening, "opening")
        @unknown default: (.opening, "unknown_surface")
        }
    }

    static func confidence(_ confidence: CapturedRoom.Confidence) -> Float {
        switch confidence {
        case .high: 0.9
        case .medium: 0.6
        case .low: 0.3
        @unknown default: 0.3
        }
    }

    static func categoryName(_ category: CapturedRoom.Object.Category) -> String {
        switch category {
        case .storage: "storage"
        case .refrigerator: "refrigerator"
        case .stove: "stove"
        case .bed: "bed"
        case .sink: "sink"
        case .washerDryer: "washer_dryer"
        case .toilet: "toilet"
        case .bathtub: "bathtub"
        case .oven: "oven"
        case .dishwasher: "dishwasher"
        case .table: "table"
        case .sofa: "sofa"
        case .chair: "chair"
        case .fireplace: "fireplace"
        case .television: "television"
        case .stairs: "stairs"
        @unknown default: "object"
        }
    }
}
