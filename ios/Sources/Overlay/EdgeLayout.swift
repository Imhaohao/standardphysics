import simd

/// One straight stroke of an outline, as a thin box along a local axis.
nonisolated struct EdgeStroke: Sendable, Equatable {
    let center: SIMD3<Float>
    let length: Float
    /// 0 = x, 1 = y, 2 = z.
    let axis: Int
}

nonisolated enum EdgeLayout {
    static let dashesPerEdge = 4

    /// Strokes outlining a box (12 edges) or a planar rectangle in local X/Y (4 edges).
    static func strokes(dimensions: SIMD3<Float>, isPlanar: Bool, isDashed: Bool) -> [EdgeStroke] {
        let edges = isPlanar ? rectangleEdges(dimensions) : boxEdges(dimensions)
        let dashCount = isDashed ? dashesPerEdge : 1
        return edges.flatMap { dashes(along: $0, count: dashCount) }
    }

    static func dashes(along edge: EdgeStroke, count: Int) -> [EdgeStroke] {
        guard count > 1 else { return [edge] }
        let dashLength = edge.length / Float(count * 2 - 1)
        var direction = SIMD3<Float>(repeating: 0)
        direction[edge.axis] = 1
        return (0..<count).map { index in
            let offset = -edge.length / 2 + dashLength * (Float(index * 2) + 0.5)
            return EdgeStroke(center: edge.center + direction * offset, length: dashLength, axis: edge.axis)
        }
    }

    private static func rectangleEdges(_ dimensions: SIMD3<Float>) -> [EdgeStroke] {
        let half = dimensions / 2
        return [-half.y, half.y].map { EdgeStroke(center: SIMD3(0, $0, 0), length: dimensions.x, axis: 0) }
            + [-half.x, half.x].map { EdgeStroke(center: SIMD3($0, 0, 0), length: dimensions.y, axis: 1) }
    }

    private static func boxEdges(_ dimensions: SIMD3<Float>) -> [EdgeStroke] {
        (0..<3).flatMap { axis in
            let others = [0, 1, 2].filter { $0 != axis }
            return cornerSigns.map { signs in
                var center = SIMD3<Float>(repeating: 0)
                center[others[0]] = signs.x * dimensions[others[0]] / 2
                center[others[1]] = signs.y * dimensions[others[1]] / 2
                return EdgeStroke(center: center, length: dimensions[axis], axis: axis)
            }
        }
    }

    private static let cornerSigns: [SIMD2<Float>] = [SIMD2(-1, -1), SIMD2(1, -1), SIMD2(1, 1), SIMD2(-1, 1)]
}
