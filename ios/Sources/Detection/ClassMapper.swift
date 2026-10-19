import Foundation

/// Maps raw detector labels onto the app's object categories (`rules/metrics.json`).
/// A label that maps to nothing is ignored. `obstacle` is drawn nowhere and checked by nothing
/// because the catalog has no generic obstacle category.
nonisolated struct ClassMapper: Sendable {
    static let obstacle = "obstacle"

    /// The detector's 80 COCO class ids in order, spelled the way `coco` below expects.
    static let cocoLabelsByClassID = [
        "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
        "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
        "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
        "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
        "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
        "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
        "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
        "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors",
        "teddy bear", "hair drier", "toothbrush",
    ]

    static let coco = ClassMapper(categoriesByLabel: [
        "dining table": "table",
        "chair": "chair",
        "couch": "sofa",
        "bench": "bench",
        "toilet": "toilet",
        "sink": "sink",
        "tv": "television",
        "refrigerator": "refrigerator",
        "microwave": "microwave",
        "oven": "oven",
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
        "signage": "sign",
        "door hardware": "door_hardware",
        "threshold": "threshold",
    ])

    static let standard = coco.merging(accessibilityFixtures)

    /// Categories the rules engine knows, i.e. every mapped id except `obstacle`.
    static let engineCategories = Set(standard.categoriesByLabel.values).subtracting([obstacle])

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
