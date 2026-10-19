import simd

nonisolated enum SceneShapeStyle: Sendable, Hashable {
    case wall
    case opening
    case window
    case object
    case detectedObject

    var isPlanar: Bool {
        [.wall, .opening, .window].contains(self)
    }
}

/// One thing drawn in 3D: a planar element or a wire box, keyed by a stable id for diffing.
nonisolated struct SceneShape: Sendable, Equatable, Identifiable {
    let id: String
    let style: SceneShapeStyle
    let transform: simd_float4x4
    let dimensions: SIMD3<Float>
}

nonisolated enum SceneShapeBuilder {
    /// A detection this close to a RoomPlan object is the same thing seen twice.
    static let duplicateRadius: Float = 0.4
    /// Detection ids snap to this grid so a jittering box keeps its entity.
    static let detectionIDGrid: Float = 0.25

    static func shapes(elements: [LiveElement], detections: [Detection]) -> [SceneShape] {
        let all = elements.compactMap(shape(for:)) + detectorOnly(detections, elements: elements).compactMap(shape(for:))
        var seen = Set<String>()
        return all.filter { seen.insert($0.id).inserted }
    }

    static func shape(for element: LiveElement) -> SceneShape? {
        guard let style = style(for: element.kind) else { return nil }
        return SceneShape(id: element.id, style: style, transform: element.transform, dimensions: element.dimensions)
    }

    static func shape(for detection: Detection) -> SceneShape? {
        guard let center = detection.worldCenter, let size = detection.worldSize else { return nil }
        var transform = matrix_identity_float4x4
        transform.columns.3 = SIMD4(center, 1)
        return SceneShape(id: detectionID(detection, center: center), style: .detectedObject, transform: transform, dimensions: size)
    }

    static func detectorOnly(_ detections: [Detection], elements: [LiveElement]) -> [Detection] {
        let objectCenters = elements.filter { $0.kind == .object }.map { PlanGeometry.worldPoint(.zero, transform: $0.transform) }
        return detections.filter { detection in
            guard let center = detection.worldCenter else { return false }
            return !objectCenters.contains { simd_distance($0, center) < duplicateRadius }
        }
    }

    private static func style(for kind: ElementKind) -> SceneShapeStyle? {
        switch kind {
        case .wall: .wall
        case .door, .opening: .opening
        case .window: .window
        case .object: .object
        case .floor: nil
        }
    }

    private static func detectionID(_ detection: Detection, center: SIMD3<Float>) -> String {
        let cell = (center / detectionIDGrid).rounded(.toNearestOrAwayFromZero)
        return "detection:\(detection.category):\(Int(cell.x)),\(Int(cell.y)),\(Int(cell.z))"
    }
}
