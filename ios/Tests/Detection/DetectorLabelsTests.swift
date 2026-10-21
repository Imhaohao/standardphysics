import CoreML
import XCTest
@testable import StandardPhysics

final class DetectorLabelsTests: XCTestCase {
    /// The `labels` metadata `export-detector.sh` writes for the published D-FINE COCO weights.
    private static let publishedCocoLabels = """
    person,bicycle,car,motorbike,aeroplane,bus,train,truck,boat,traffic light,fire hydrant,stop sign,parking meter,\
    bench,bird,cat,dog,horse,sheep,cow,elephant,bear,zebra,giraffe,backpack,umbrella,handbag,tie,suitcase,frisbee,\
    skis,snowboard,sports ball,kite,baseball bat,baseball glove,skateboard,surfboard,tennis racket,bottle,wine glass,\
    cup,fork,knife,spoon,bowl,banana,apple,sandwich,orange,broccoli,carrot,hot dog,pizza,donut,cake,chair,sofa,\
    pottedplant,bed,diningtable,toilet,tvmonitor,laptop,mouse,remote,keyboard,cell phone,microwave,oven,toaster,\
    sink,refrigerator,book,clock,vase,scissors,teddy bear,hair drier,toothbrush
    """

    func testModelWithoutLabelsIsReadAsCoco() {
        XCTAssertEqual(DetectorLabels.labelsByClassID(fromCreatorMetadata: [:]), ClassMapper.cocoLabelsByClassID)
        XCTAssertEqual(
            DetectorLabels.labelsByClassID(fromCreatorMetadata: ["source": "https://example.com"]),
            ClassMapper.cocoLabelsByClassID
        )
    }

    func testBlankLabelsAreReadAsCoco() {
        XCTAssertEqual(DetectorLabels.labelsByClassID(fromCreatorMetadata: ["labels": ""]), ClassMapper.cocoLabelsByClassID)
        XCTAssertEqual(DetectorLabels.labelsByClassID(fromCreatorMetadata: ["labels": " , "]), ClassMapper.cocoLabelsByClassID)
    }

    func testFineTunedLabelsAreSplitInClassIDOrder() {
        let metadata = ["labels": "chair,countertop, door handle ,grab bar,power plugs and sockets"]
        XCTAssertEqual(
            DetectorLabels.labelsByClassID(fromCreatorMetadata: metadata),
            ["chair", "countertop", "door handle", "grab bar", "power plugs and sockets"]
        )
    }

    func testPublishedCocoLabelsKeepEightyClassIDs() {
        let labels = DetectorLabels.labelsByClassID(fromCreatorMetadata: ["labels": Self.publishedCocoLabels])
        XCTAssertEqual(labels.count, ClassMapper.cocoLabelsByClassID.count)
        XCTAssertEqual(labels[56], "chair")
        XCTAssertEqual(labels[62], "tvmonitor")
    }

    func testDecoderNamesClassIDsFromFineTunedLabels() {
        let labels = DetectorLabels.labelsByClassID(fromCreatorMetadata: ["labels": "chair,door handle,grab bar,person"])
        let decoder = DetectorOutputDecoder(labelsByClassID: labels, mapper: .standard, minimumConfidence: 0.5)
        let output = DetectorOutput(
            scores: [0.9, 0.8, 0.7],
            classIDs: [2, 1, 3],
            boxes: [0.5, 0.5, 0.1, 0.4, 0.2, 0.5, 0.05, 0.05, 0.5, 0.5, 0.2, 0.6]
        )
        let detections = decoder.detections(from: output)
        XCTAssertEqual(detections.map(\.label), ["grab bar", "door handle"])
        XCTAssertEqual(detections.map(\.category), ["grab_bar", "door_hardware"])
    }

    func testDecoderMapsThePublishedCocoSpellings() {
        let labels = DetectorLabels.labelsByClassID(fromCreatorMetadata: ["labels": Self.publishedCocoLabels])
        let decoder = DetectorOutputDecoder(labelsByClassID: labels, mapper: .standard, minimumConfidence: 0.5)
        let output = DetectorOutput(
            scores: [0.9, 0.8],
            classIDs: [57, 60],
            boxes: [0.3, 0.5, 0.2, 0.2, 0.7, 0.5, 0.2, 0.2]
        )
        XCTAssertEqual(decoder.detections(from: output).map(\.category), ["sofa", "table"])
    }

    func testBundledModelDeclaresLabelsTheMapperUnderstands() throws {
        guard let url = Bundle.main.url(forResource: CoreMLDetector.modelResourceName, withExtension: "mlmodelc") else {
            throw XCTSkip("No ObjectDetector model bundled; run ios/scripts/export-detector.sh")
        }
        let model = try MLModel(contentsOf: url)
        let labels = DetectorLabels.labelsByClassID(of: model)
        let mappedCategories = Set(labels.compactMap { ClassMapper.standard.category(for: $0) })
        XCTAssertTrue(mappedCategories.isSuperset(of: ["chair", "table", "sofa", "television"]), "\(mappedCategories)")
    }
}
