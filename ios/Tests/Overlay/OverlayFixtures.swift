import simd
@testable import StandardPhysics

enum OverlayFixtures {
    static func element(
        _ id: String,
        kind: ElementKind,
        category: String = "",
        center: SIMD3<Float>,
        size: SIMD3<Float>,
        yaw: Float = 0,
        source: ElementSource = .roomplan
    ) -> LiveElement {
        var transform = simd_float4x4(simd_quatf(angle: yaw, axis: SIMD3(0, 1, 0)))
        transform.columns.3 = SIMD4(center, 1)
        return LiveElement(id: id, kind: kind, category: category, transform: transform, dimensions: size, confidence: 1, source: source)
    }

    static func finding(_ subjectID: String, _ status: FindingStatus, section: String = "11B-902.3") -> Finding {
        Finding(
            ruleID: "rule-\(section)",
            jurisdiction: .cbc11b,
            section: section,
            subjectID: subjectID,
            status: status,
            measured: nil,
            required: "",
            message: ""
        )
    }

    /// A 4 m x 3 m room with the floor at y = 0, a counter, a table and a door.
    static let shop: [LiveElement] = [
        element("wall-north", kind: .wall, center: SIMD3(0, 1.25, -1.5), size: SIMD3(4, 2.5, 0)),
        element("wall-west", kind: .wall, center: SIMD3(-2, 1.25, 0), size: SIMD3(3, 2.5, 0), yaw: .pi / 2),
        element("door-1", kind: .door, category: "door", center: SIMD3(1, 1.03, 1.5), size: SIMD3(0.86, 2.06, 0)),
        element("counter-1", kind: .object, category: "counter", center: SIMD3(-1.5, 0.48, -1.2), size: SIMD3(1.2, 0.96, 0.6)),
        element("table-1", kind: .object, category: "table", center: SIMD3(0.5, 0.37, -0.2), size: SIMD3(0.8, 0.74, 0.8)),
    ]
}
