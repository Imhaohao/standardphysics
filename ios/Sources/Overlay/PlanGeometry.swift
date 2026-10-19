import simd

/// A straight run on the floor plan, in world X/Z metres.
nonisolated struct PlanSegment: Sendable, Equatable {
    let start: SIMD2<Float>
    let end: SIMD2<Float>

    var length: Float { simd_distance(start, end) }
}

nonisolated struct PlanGap: Sendable, Equatable {
    let pointOnFirst: SIMD2<Float>
    let pointOnSecond: SIMD2<Float>

    var distance: Float { simd_distance(pointOnFirst, pointOnSecond) }
    var midpoint: SIMD2<Float> { (pointOnFirst + pointOnSecond) / 2 }
}

nonisolated enum PlanGeometry {
    static func planPoint(_ point: SIMD3<Float>) -> SIMD2<Float> {
        SIMD2(point.x, point.z)
    }

    static func worldPoint(_ local: SIMD3<Float>, transform: simd_float4x4) -> SIMD3<Float> {
        let world = transform * SIMD4(local, 1)
        return SIMD3(world.x, world.y, world.z)
    }

    /// The four floor corners of a box whose local axes are width (x), height (y), depth (z).
    static func footprint(transform: simd_float4x4, dimensions: SIMD3<Float>) -> [SIMD2<Float>] {
        let halfWidth = dimensions.x / 2
        let halfDepth = dimensions.z / 2
        let localCorners: [SIMD3<Float>] = [
            SIMD3(-halfWidth, 0, -halfDepth),
            SIMD3(halfWidth, 0, -halfDepth),
            SIMD3(halfWidth, 0, halfDepth),
            SIMD3(-halfWidth, 0, halfDepth),
        ]
        return localCorners.map { planPoint(worldPoint($0, transform: transform)) }
    }

    /// The floor line of a planar element (wall, door, window) that spans its local X axis.
    static func planarSegment(transform: simd_float4x4, dimensions: SIMD3<Float>) -> PlanSegment {
        let halfWidth = dimensions.x / 2
        return PlanSegment(
            start: planPoint(worldPoint(SIMD3(-halfWidth, 0, 0), transform: transform)),
            end: planPoint(worldPoint(SIMD3(halfWidth, 0, 0), transform: transform))
        )
    }

    static func edges(of polygon: [SIMD2<Float>]) -> [PlanSegment] {
        polygon.indices.map { PlanSegment(start: polygon[$0], end: polygon[($0 + 1) % polygon.count]) }
    }

    /// The shortest gap between two outlines, or nil when they touch or overlap.
    static func gap(between first: [PlanSegment], and second: [PlanSegment]) -> PlanGap? {
        let candidates = first.flatMap { edge in second.map { closestPoints(edge, $0) } }
        guard let shortest = candidates.min(by: { $0.distance < $1.distance }), shortest.distance > 0 else { return nil }
        guard !contains(outline: first, point: second.first?.start) else { return nil }
        guard !contains(outline: second, point: first.first?.start) else { return nil }
        return shortest
    }

    static func closestPoints(_ first: PlanSegment, _ second: PlanSegment) -> PlanGap {
        if intersects(first, second) {
            let crossing = closestPoint(on: first, to: second.start)
            return PlanGap(pointOnFirst: crossing, pointOnSecond: crossing)
        }
        let candidates = [
            PlanGap(pointOnFirst: first.start, pointOnSecond: closestPoint(on: second, to: first.start)),
            PlanGap(pointOnFirst: first.end, pointOnSecond: closestPoint(on: second, to: first.end)),
            PlanGap(pointOnFirst: closestPoint(on: first, to: second.start), pointOnSecond: second.start),
            PlanGap(pointOnFirst: closestPoint(on: first, to: second.end), pointOnSecond: second.end),
        ]
        return candidates.min { $0.distance < $1.distance } ?? candidates[0]
    }

    static func closestPoint(on segment: PlanSegment, to point: SIMD2<Float>) -> SIMD2<Float> {
        let direction = segment.end - segment.start
        let lengthSquared = simd_length_squared(direction)
        guard lengthSquared > 0 else { return segment.start }
        let along = simd_clamp(simd_dot(point - segment.start, direction) / lengthSquared, 0, 1)
        return segment.start + direction * along
    }

    static func intersects(_ first: PlanSegment, _ second: PlanSegment) -> Bool {
        let d1 = orientation(second.start, second.end, first.start)
        let d2 = orientation(second.start, second.end, first.end)
        let d3 = orientation(first.start, first.end, second.start)
        let d4 = orientation(first.start, first.end, second.end)
        return d1 * d2 < 0 && d3 * d4 < 0
    }

    /// Even-odd test against a closed outline; open outlines (a single wall) never contain anything.
    static func contains(outline: [PlanSegment], point: SIMD2<Float>?) -> Bool {
        guard let point, outline.count >= 3 else { return false }
        let crossings = outline.filter { edge in
            (edge.start.y > point.y) != (edge.end.y > point.y)
                && point.x < (edge.end.x - edge.start.x) * (point.y - edge.start.y) / (edge.end.y - edge.start.y) + edge.start.x
        }
        return !crossings.count.isMultiple(of: 2)
    }

    private static func orientation(_ a: SIMD2<Float>, _ b: SIMD2<Float>, _ c: SIMD2<Float>) -> Float {
        (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
    }
}
