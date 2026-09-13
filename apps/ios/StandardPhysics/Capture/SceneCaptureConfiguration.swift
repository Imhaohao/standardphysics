import ARKit

enum SceneReconstructionMode: Equatable, Sendable {
    case mesh
    case meshWithClassification
}

struct SceneCaptureCapabilities: Equatable, Sendable {
    let supportsMesh: Bool
    let supportsMeshWithClassification: Bool
    let supportsPersonSegmentationWithDepth: Bool
    let supportsPersonSegmentation: Bool

    init(
        supportsMesh: Bool,
        supportsMeshWithClassification: Bool,
        supportsPersonSegmentationWithDepth: Bool,
        supportsPersonSegmentation: Bool
    ) {
        self.supportsMesh = supportsMesh
        self.supportsMeshWithClassification = supportsMeshWithClassification
        self.supportsPersonSegmentationWithDepth = supportsPersonSegmentationWithDepth
        self.supportsPersonSegmentation = supportsPersonSegmentation
    }

    static var current: Self {
        Self(
            supportsMesh: ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh),
            supportsMeshWithClassification: ARWorldTrackingConfiguration
                .supportsSceneReconstruction(.meshWithClassification),
            supportsPersonSegmentationWithDepth: ARWorldTrackingConfiguration
                .supportsFrameSemantics(.personSegmentationWithDepth),
            supportsPersonSegmentation: ARWorldTrackingConfiguration
                .supportsFrameSemantics(.personSegmentation)
        )
    }
}

struct SceneCaptureOptions: Equatable, Sendable {
    let reconstruction: SceneReconstructionMode?
    let usesPersonSegmentationWithDepth: Bool
    let usesPersonSegmentation: Bool

    var peopleFilteringEnabled: Bool {
        usesPersonSegmentationWithDepth || usesPersonSegmentation
    }

    static func select(from capabilities: SceneCaptureCapabilities) -> Self {
        let reconstruction: SceneReconstructionMode?
        if capabilities.supportsMeshWithClassification {
            reconstruction = .meshWithClassification
        } else if capabilities.supportsMesh {
            reconstruction = .mesh
        } else {
            reconstruction = nil
        }

        if capabilities.supportsPersonSegmentationWithDepth {
            return Self(
                reconstruction: reconstruction,
                usesPersonSegmentationWithDepth: true,
                usesPersonSegmentation: false
            )
        }
        return Self(
            reconstruction: reconstruction,
            usesPersonSegmentationWithDepth: false,
            usesPersonSegmentation: capabilities.supportsPersonSegmentation
        )
    }
}

enum SceneCaptureConfiguration {
    struct Prepared {
        let configuration: ARWorldTrackingConfiguration
        let options: SceneCaptureOptions
    }

    static func prepare() -> Prepared {
        let options = SceneCaptureOptions.select(from: .current)
        let configuration = ARWorldTrackingConfiguration()
        if let reconstruction = options.reconstruction {
            switch reconstruction {
            case .mesh:
                configuration.sceneReconstruction = .mesh
            case .meshWithClassification:
                configuration.sceneReconstruction = .meshWithClassification
            }
        }
        if options.usesPersonSegmentationWithDepth {
            configuration.frameSemantics.insert(.personSegmentationWithDepth)
        } else if options.usesPersonSegmentation {
            configuration.frameSemantics.insert(.personSegmentation)
        }
        return Prepared(configuration: configuration, options: options)
    }
}
