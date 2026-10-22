import simd

/// Which RoomPlan objects get a photo crop for the server to check. RoomPlan reports ordering
/// counters as `storage` or `table` and built-in benches as `sofa` or `chair`, so those
/// categories, and anything whose top sits at counter height, are worth a second look.
nonisolated enum RelabelSelection {
    static let maximumPerRoom = 20
    static let doubtfulCategories: Set<String> = ["storage", "table", "sofa", "chair", "bed"]
    /// 28 in to 48 in above the floor: from a low counter to a bar top.
    static let counterTopHeights: ClosedRange<Float> = 0.7112...1.2192

    static func topHeight(of object: CapturedRoomGeometry.PlannedObject, floorLevel: Float) -> Float {
        object.transform.columns.3.y + object.dimensions.y / 2 - floorLevel
    }

    static func isCounterHeight(_ object: CapturedRoomGeometry.PlannedObject, floorLevel: Float) -> Bool {
        counterTopHeights.contains(topHeight(of: object, floorLevel: floorLevel))
    }

    static func isDoubtful(_ object: CapturedRoomGeometry.PlannedObject, floorLevel: Float) -> Bool {
        !object.identifier.isEmpty
            && (doubtfulCategories.contains(object.category) || isCounterHeight(object, floorLevel: floorLevel))
    }

    /// Counter-height objects first, then larger footprints, at most `maximumPerRoom`.
    static func candidates(in room: CapturedRoomGeometry) -> [CapturedRoomGeometry.PlannedObject] {
        let doubtful = room.objects.filter { isDoubtful($0, floorLevel: room.floorLevel) }
        let ranked = doubtful.sorted { first, second in
            let firstAtCounter = isCounterHeight(first, floorLevel: room.floorLevel)
            let secondAtCounter = isCounterHeight(second, floorLevel: room.floorLevel)
            if firstAtCounter != secondAtCounter { return firstAtCounter }
            return footprint(first) > footprint(second)
        }
        return Array(ranked.prefix(maximumPerRoom))
    }

    private static func footprint(_ object: CapturedRoomGeometry.PlannedObject) -> Float {
        object.dimensions.x * object.dimensions.z
    }
}
