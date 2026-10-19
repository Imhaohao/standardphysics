import CoreML
import Foundation
import Vision

/// Runs the bundled D-FINE Core ML detector through Vision. With no model in the bundle it reports nothing.
/// Vision stretches the frame to the model's square input, as in training, so the model's normalized
/// boxes map straight back onto the captured image.
actor CoreMLDetector {
    nonisolated static let modelResourceName = "ObjectDetector"
    nonisolated static let defaultMinimumConfidence: Float = 0.4

    private enum OutputName {
        static let scores = "scores"
        static let classIDs = "classIDs"
        static let boxes = "boxes"
    }

    private let bundle: Bundle
    private let decoder: DetectorOutputDecoder
    private var request: CoreMLRequest?
    private var hasAttemptedLoad = false

    init(bundle: Bundle = .main, mapper: ClassMapper = .standard, minimumConfidence: Float = defaultMinimumConfidence) {
        self.bundle = bundle
        decoder = DetectorOutputDecoder(
            labelsByClassID: ClassMapper.cocoLabelsByClassID,
            mapper: mapper,
            minimumConfidence: minimumConfidence
        )
    }

    var isModelAvailable: Bool {
        loadedRequest() != nil
    }

    func detect(pixelBuffer: CVPixelBufferWrapper) async throws -> [Detection] {
        guard let request = loadedRequest() else { return [] }
        let observations = try await request.perform(on: pixelBuffer.buffer, orientation: .up)
        guard let output = Self.output(from: observations) else { return [] }
        return decoder.detections(from: output)
    }

    private static func output(from observations: [any VisionObservation]) -> DetectorOutput? {
        let valuesByName = Dictionary(
            observations.compactMap { $0 as? CoreMLFeatureValueObservation }.map { ($0.featureName, $0.featureValue) },
            uniquingKeysWith: { first, _ in first }
        )
        guard let scores = valuesByName[OutputName.scores]?.shapedArrayValue(of: Float.self),
              let classIDs = valuesByName[OutputName.classIDs]?.shapedArrayValue(of: Int32.self),
              let boxes = valuesByName[OutputName.boxes]?.shapedArrayValue(of: Float.self)
        else { return nil }
        return DetectorOutput(scores: scores.scalars, classIDs: classIDs.scalars, boxes: boxes.scalars)
    }

    private func loadedRequest() -> CoreMLRequest? {
        if hasAttemptedLoad { return request }
        hasAttemptedLoad = true
        request = Self.makeRequest(bundle: bundle)
        return request
    }

    private nonisolated static func makeRequest(bundle: Bundle) -> CoreMLRequest? {
        guard let url = bundle.url(forResource: modelResourceName, withExtension: "mlmodelc") else { return nil }
        let configuration = MLModelConfiguration()
        configuration.computeUnits = .all
        guard let model = try? MLModel(contentsOf: url, configuration: configuration),
              let container = try? CoreMLModelContainer(model: model)
        else { return nil }
        var request = CoreMLRequest(model: container)
        request.cropAndScaleAction = .scaleToFill
        return request
    }
}

/// Declared apart from the actor so the protocol's inferred main-actor isolation does not leak onto `init`.
extension CoreMLDetector: ObjectDetecting {}
