import Foundation

/// Maps raw detector labels onto the app's object categories (`rules/metrics.json`).
/// A label that maps to nothing is ignored by the overlay.
nonisolated struct ClassMapper: Sendable {
    static let obstacle = "obstacle"

    static let coco = ClassMapper(categoriesByLabel: [
        "dining table": "table",
        "chair": "chair",
        "couch": "sofa",
        "bench": "bench",
        "toilet": "toilet",
        "sink": "sink",
        "tv": "television",
        "refrigerator": "refrigerator",
        "oven": "oven",
        "microwave": "microwave",
        "bed": "bed",
        "potted plant": obstacle,
        "suitcase": obstacle,
        "backpack": obstacle,
        "handbag": obstacle,
        "umbrella": obstacle,
        "bicycle": obstacle,
        "fire hydrant": obstacle,
        "vase": obstacle,
    ])

    /// Labels a future accessibility-specific model is expected to emit.
    static let accessibilityFixtures = ClassMapper(categoriesByLabel: [
        "counter": "counter",
        "grab bar": "grab_bar",
        "signage": "signage",
        "door hardware": "door_hardware",
        "threshold": "threshold",
    ])

    static let standard = coco.merging(accessibilityFixtures)

    let categoriesByLabel: [String: String]

    func category(for label: String) -> String? {
        categoriesByLabel[Self.normalized(label)]
    }

    func merging(_ other: ClassMapper) -> ClassMapper {
        ClassMapper(categoriesByLabel: categoriesByLabel.merging(other.categoriesByLabel) { _, newer in newer })
    }

    private static func normalized(_ label: String) -> String {
        label.lowercased()
            .replacingOccurrences(of: "_", with: " ")
            .trimmingCharacters(in: .whitespaces)
    }
}
