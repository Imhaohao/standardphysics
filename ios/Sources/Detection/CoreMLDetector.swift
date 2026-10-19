import CoreML
import Foundation
import Vision

/// Runs the bundled Core ML detector through Vision. With no model in the bundle it reports nothing.
actor CoreMLDetector {
    nonisolated static let modelResourceName = "ObjectDetector"
    nonisolated static let defaultMinimumConfidence: Float = 0.4

    private let bundle: Bundle
    private let mapper: ClassMapper
    private let minimumConfidence: Float
    private var request: CoreMLRequest?
    private var hasAttemptedLoad = false

    init(bundle: Bundle = .main, mapper: ClassMapper = .standard, minimumConfidence: Float = defaultMinimumConfidence) {
        self.bundle = bundle
        self.mapper = mapper
        self.minimumConfidence = minimumConfidence
    }

    var isModelAvailable: Bool {
        loadedRequest() != nil
    }

    func detect(pixelBuffer: CVPixelBufferWrapper) async throws -> [Detection] {
        guard let request = loadedRequest() else { return [] }
        let observations = try await request.perform(on: pixelBuffer.buffer, orientation: .up)
        return observations
            .compactMap { $0 as? RecognizedObjectObservation }
            .compactMap(detection(from:))
    }

    private func detection(from observation: RecognizedObjectObservation) -> Detection? {
        guard let best = observation.labels.first, best.confidence >= minimumConfidence else { return nil }
        guard let category = mapper.category(for: best.identifier) else { return nil }
        return Detection(
            label: best.identifier,
            category: category,
            confidence: best.confidence,
            boundingBox: observation.boundingBox.verticallyFlipped().cgRect,
            worldCenter: nil,
            worldSize: nil
        )
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
        request.cropAndScaleAction = .scaleToFit
        return request
    }
}

/// Declared apart from the actor so the protocol's inferred main-actor isolation does not leak onto `init`.
extension CoreMLDetector: ObjectDetecting {}
