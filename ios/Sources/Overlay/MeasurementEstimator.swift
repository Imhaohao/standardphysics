import simd

nonisolated enum MeasurementKind: String, Sendable, Equatable {
    case topHeight
    case clearWidth
    case passageWidth
}

/// One provisional number shown while scanning. The Rust engine produces the real findings later.
nonisolated struct LiveMeasurement: Sendable, Equatable, Identifiable {
    let kind: MeasurementKind
    let subjectID: String
    let meters: Float
    /// Where the label pins, in world space.
    let anchor: SIMD3<Float>
    /// Ends of the dimension line, when the measurement spans two points.
    let span: [SIMD3<Float>]

    var id: String { "\(kind.rawValue):\(subjectID)" }
}

nonisolated struct PlanFootprint: Sendable, Equatable {
    let id: String
    let category: String
    let corners: [SIMD2<Float>]
}

nonisolated struct PlanOpening: Sendable, Equatable {
    let id: String
    let kind: ElementKind
    let segment: PlanSegment
}

nonisolated struct FloorPlan: Sendable, Equatable {
    var walls: [PlanSegment] = []
    var openings: [PlanOpening] = []
    var objects: [PlanFootprint] = []
}

nonisolated struct LiveMeasurements: Sendable, Equatable {
    static let empty = LiveMeasurements(floorHeight: 0, measurements: [], plan: FloorPlan())

    let floorHeight: Float
    let measurements: [LiveMeasurement]
    let plan: FloorPlan
}

nonisolated enum MeasurementEstimator {
    /// Gaps narrower than this are furniture pushed together, not a way through.
    static let minimumPassage: Float = 0.1
    /// Gaps wider than this are open floor, not a passage worth flagging.
    static let maximumPassage: Float = 2.5
    /// Objects whose underside sits higher than this above the floor do not block walking.
    static let floorStandingClearance: Float = 0.3

    static func estimate(from elements: [LiveElement]) -> LiveMeasurements {
        let floorHeight = floorHeight(of: elements)
        let objects = elements.filter { $0.kind == .object }
        let openings = elements.filter { [.door, .opening].contains($0.kind) }
        let measurements = objects.map { topHeight(of: $0, floorHeight: floorHeight) }
            + openings.map(clearWidth(of:))
            + [narrowestPassage(in: elements, floorHeight: floorHeight)].compactMap { $0 }
        return LiveMeasurements(floorHeight: floorHeight, measurements: measurements, plan: plan(of: elements))
    }

    static func floorHeight(of elements: [LiveElement]) -> Float {
        if let floor = elements.first(where: { $0.kind == .floor }) {
            return floor.transform.columns.3.y
        }
        let walls = elements.filter { $0.kind == .wall }
        let bottoms = (walls.isEmpty ? elements : walls).map(bottomHeight(of:))
        return bottoms.min() ?? 0
    }

    static func topHeight(of object: LiveElement, floorHeight: Float) -> LiveMeasurement {
        let center = object.transform.columns.3
        let top = center.y + object.dimensions.y / 2
        return LiveMeasurement(
            kind: .topHeight,
            subjectID: object.id,
            meters: top - floorHeight,
            anchor: SIMD3(center.x, top, center.z),
            span: []
        )
    }

    static func clearWidth(of opening: LiveElement) -> LiveMeasurement {
        let halfWidth = opening.dimensions.x / 2
        return LiveMeasurement(
            kind: .clearWidth,
            subjectID: opening.id,
            meters: opening.dimensions.x,
            anchor: PlanGeometry.worldPoint(.zero, transform: opening.transform),
            span: [
                PlanGeometry.worldPoint(SIMD3(-halfWidth, 0, 0), transform: opening.transform),
                PlanGeometry.worldPoint(SIMD3(halfWidth, 0, 0), transform: opening.transform),
            ]
        )
    }

    static func narrowestPassage(in elements: [LiveElement], floorHeight: Float) -> LiveMeasurement? {
        let obstacles = elements.filter { isFloorStanding($0, floorHeight: floorHeight) }
        let walls = elements.filter { $0.kind == .wall }
        let pairs = obstacles.indices.flatMap { index in
            (obstacles[(index + 1)...] + walls).map { (obstacles[index], $0) }
        }
        let narrowest = pairs
            .compactMap { pair in passageGap(pair.0, pair.1).map { (pair, $0) } }
            .filter { (minimumPassage...maximumPassage).contains($0.1.distance) }
            .min { $0.1.distance < $1.1.distance }
        guard let (pair, gap) = narrowest else { return nil }
        let lift = { (point: SIMD2<Float>) in SIMD3(point.x, floorHeight, point.y) }
        return LiveMeasurement(
            kind: .passageWidth,
            subjectID: "\(pair.0.id)|\(pair.1.id)",
            meters: gap.distance,
            anchor: lift(gap.midpoint),
            span: [lift(gap.pointOnFirst), lift(gap.pointOnSecond)]
        )
    }

    static func plan(of elements: [LiveElement]) -> FloorPlan {
        elements.reduce(into: FloorPlan()) { plan, element in
            switch element.kind {
            case .wall:
                plan.walls.append(PlanGeometry.planarSegment(transform: element.transform, dimensions: element.dimensions))
            case .door, .window, .opening:
                let segment = PlanGeometry.planarSegment(transform: element.transform, dimensions: element.dimensions)
                plan.openings.append(PlanOpening(id: element.id, kind: element.kind, segment: segment))
            case .object:
                let corners = PlanGeometry.footprint(transform: element.transform, dimensions: element.dimensions)
                plan.objects.append(PlanFootprint(id: element.id, category: element.category, corners: corners))
            case .floor:
                break
            }
        }
    }

    private static func bottomHeight(of element: LiveElement) -> Float {
        element.transform.columns.3.y - element.dimensions.y / 2
    }

    private static func isFloorStanding(_ element: LiveElement, floorHeight: Float) -> Bool {
        element.kind == .object && bottomHeight(of: element) - floorHeight <= floorStandingClearance
    }

    private static func passageGap(_ first: LiveElement, _ second: LiveElement) -> PlanGap? {
        PlanGeometry.gap(between: outline(of: first), and: outline(of: second))
    }

    private static func outline(of element: LiveElement) -> [PlanSegment] {
        guard element.kind == .object else {
            return [PlanGeometry.planarSegment(transform: element.transform, dimensions: element.dimensions)]
        }
        return PlanGeometry.edges(of: PlanGeometry.footprint(transform: element.transform, dimensions: element.dimensions))
    }
}
