import CoreML
import Foundation

/// The class labels a detector declares, in class-id order. The export scripts write them, comma
/// separated, under the creator-defined metadata key `labels`; a model without them is taken to be COCO.
nonisolated enum DetectorLabels {
    static let metadataKey = "labels"

    static func labelsByClassID(of model: MLModel) -> [String] {
        let creatorMetadata = model.modelDescription.metadata[.creatorDefinedKey] as? [String: String]
        return labelsByClassID(fromCreatorMetadata: creatorMetadata ?? [:])
    }

    static func labelsByClassID(fromCreatorMetadata metadata: [String: String]) -> [String] {
        guard let joinedLabels = metadata[metadataKey] else { return ClassMapper.cocoLabelsByClassID }
        let labels = joinedLabels
            .split(separator: ",", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespaces) }
        let declaresAnyLabel = labels.contains { !$0.isEmpty }
        return declaresAnyLabel ? labels : ClassMapper.cocoLabelsByClassID
    }
}
