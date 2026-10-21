import CoreML
import Foundation
import Vision

/// Runs the bundled D-FINE Core ML detector through Vision. With no model in the bundle it reports nothing.
/// Class ids are named by the labels in the model's metadata (see `DetectorLabels`).
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

    private nonisolated struct LoadedModel {
        let request: CoreMLRequest
        let decoder: DetectorOutputDecoder
    }

    private let bundle: Bundle
    private let mapper: ClassMapper
    private let minimumConfidence: Float
    private var model: LoadedModel?
    private var hasAttemptedLoad = false

    init(bundle: Bundle = .main, mapper: ClassMapper = .standard, minimumConfidence: Float = defaultMinimumConfidence) {
        self.bundle = bundle
        self.mapper = mapper
        self.minimumConfidence = minimumConfidence
    }

    var isModelAvailable: Bool {
        loadedModel() != nil
    }

    func detect(pixelBuffer: CVPixelBufferWrapper) async throws -> [Detection] {
        guard let model = loadedModel() else { return [] }
        let observations = try await model.request.perform(on: pixelBuffer.buffer, orientation: .up)
        guard let output = Self.output(from: observations) else { return [] }
        return model.decoder.detections(from: output)
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

    private func loadedModel() -> LoadedModel? {
        if hasAttemptedLoad { return model }
        hasAttemptedLoad = true
        model = makeLoadedModel()
        return model
    }

    private func makeLoadedModel() -> LoadedModel? {
        guard let url = bundle.url(forResource: Self.modelResourceName, withExtension: "mlmodelc") else { return nil }
        let configuration = MLModelConfiguration()
        configuration.computeUnits = .all
        guard let mlModel = try? MLModel(contentsOf: url, configuration: configuration),
              let container = try? CoreMLModelContainer(model: mlModel)
        else { return nil }
        var request = CoreMLRequest(model: container)
        request.cropAndScaleAction = .scaleToFill
        let decoder = DetectorOutputDecoder(
            labelsByClassID: DetectorLabels.labelsByClassID(of: mlModel),
            mapper: mapper,
            minimumConfidence: minimumConfidence
        )
        return LoadedModel(request: request, decoder: decoder)
    }
}

/// Declared apart from the actor so the protocol's inferred main-actor isolation does not leak onto `init`.
extension CoreMLDetector: ObjectDetecting {}
