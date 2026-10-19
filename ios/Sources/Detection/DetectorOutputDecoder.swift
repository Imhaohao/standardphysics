import CoreGraphics

/// The raw per-query tensors of the D-FINE model, flattened. `boxes` holds four values per query:
/// centre x, centre y, width, height, normalized to the image with origin top-left.
nonisolated struct DetectorOutput: Sendable, Equatable {
    static let valuesPerBox = 4

    let scores: [Float]
    let classIDs: [Int32]
    let boxes: [Float]
}

/// Turns the model's queries into detections. DETR-style models predict one object per query,
/// so a score threshold replaces NMS.
nonisolated struct DetectorOutputDecoder: Sendable {
    private static let unitRect = CGRect(x: 0, y: 0, width: 1, height: 1)

    let labelsByClassID: [String]
    let mapper: ClassMapper
    let minimumConfidence: Float

    func detections(from output: DetectorOutput) -> [Detection] {
        guard output.classIDs.count == output.scores.count,
              output.boxes.count == output.scores.count * DetectorOutput.valuesPerBox
        else { return [] }
        return output.scores.indices
            .filter { output.scores[$0] >= minimumConfidence }
            .compactMap { detection(at: $0, in: output) }
            .sorted { $0.confidence > $1.confidence }
    }

    private func detection(at query: Int, in output: DetectorOutput) -> Detection? {
        let classID = Int(output.classIDs[query])
        guard labelsByClassID.indices.contains(classID) else { return nil }
        let label = labelsByClassID[classID]
        guard let category = mapper.category(for: label) else { return nil }
        let box = Self.rect(fromCenterBoxAt: query * DetectorOutput.valuesPerBox, in: output.boxes)
        guard !box.isEmpty else { return nil }
        return Detection(
            label: label,
            category: category,
            confidence: output.scores[query],
            boundingBox: box,
            worldCenter: nil,
            worldSize: nil
        )
    }

    private static func rect(fromCenterBoxAt offset: Int, in boxes: [Float]) -> CGRect {
        let centerX = CGFloat(boxes[offset])
        let centerY = CGFloat(boxes[offset + 1])
        let width = CGFloat(boxes[offset + 2])
        let height = CGFloat(boxes[offset + 3])
        let rect = CGRect(x: centerX - width / 2, y: centerY - height / 2, width: width, height: height)
        let clamped = rect.intersection(unitRect)
        return clamped.isNull ? .zero : clamped
    }
}
