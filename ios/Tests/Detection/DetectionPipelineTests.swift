import CoreVideo
import XCTest
import simd
@testable import StandardPhysics

final class ClassMapperTests: XCTestCase {
    func testCocoLabelsMapToAppCategories() {
        let mapper = ClassMapper.standard
        XCTAssertEqual(mapper.category(for: "dining table"), "table")
        XCTAssertEqual(mapper.category(for: "couch"), "sofa")
        XCTAssertEqual(mapper.category(for: "tv"), "television")
        XCTAssertEqual(mapper.category(for: "Potted Plant"), ClassMapper.obstacle)
        XCTAssertEqual(mapper.category(for: "suitcase"), ClassMapper.obstacle)
    }

    func testPeopleAndUnknownLabelsAreIgnored() {
        XCTAssertNil(ClassMapper.standard.category(for: "person"))
        XCTAssertNil(ClassMapper.standard.category(for: "giraffe"))
    }

    func testFutureAccessibilityLabelsAreReserved() {
        XCTAssertEqual(ClassMapper.standard.category(for: "grab_bar"), "grab_bar")
        XCTAssertEqual(ClassMapper.standard.category(for: "door hardware"), "door_hardware")
        XCTAssertNil(ClassMapper.coco.category(for: "grab bar"))
    }
}

final class FrameThrottlerTests: XCTestCase {
    func testAdmitsEveryThirdFrame() {
        let throttler = FrameThrottler(stride: 3)
        let admitted = (0..<9).map { _ in
            let isAdmitted = throttler.admit()
            if isAdmitted { throttler.finish() }
            return isAdmitted
        }
        XCTAssertEqual(admitted, [false, false, true, false, false, true, false, false, true])
    }

    func testDropsFramesWhileBusy() {
        let throttler = FrameThrottler(stride: 2)
        XCTAssertFalse(throttler.admit())
        XCTAssertTrue(throttler.admit())
        XCTAssertFalse(throttler.admit())
        XCTAssertFalse(throttler.admit())
        XCTAssertFalse(throttler.admit())
        throttler.finish()
        XCTAssertTrue(throttler.admit())
    }
}

final class CoreMLDetectorTests: XCTestCase {
    private func blankFrame() throws -> CVPixelBufferWrapper {
        var buffer: CVPixelBuffer?
        let status = CVPixelBufferCreate(kCFAllocatorDefault, 640, 480, kCVPixelFormatType_32BGRA, nil, &buffer)
        XCTAssertEqual(status, kCVReturnSuccess)
        return CVPixelBufferWrapper(buffer: try XCTUnwrap(buffer))
    }

    func testMissingModelReportsNothing() async throws {
        let detector = CoreMLDetector(bundle: Bundle(for: Self.self))
        let isAvailable = await detector.isModelAvailable
        XCTAssertFalse(isAvailable)
        let detections = try await detector.detect(pixelBuffer: blankFrame())
        XCTAssertEqual(detections, [])
    }

    func testBundledModelRunsOnABlankFrameWhenPresent() async throws {
        let detector = CoreMLDetector(bundle: .main)
        guard await detector.isModelAvailable else {
            throw XCTSkip("No ObjectDetector model bundled; run ios/scripts/export-detector.sh")
        }
        let detections = try await detector.detect(pixelBuffer: blankFrame())
        XCTAssertTrue(detections.allSatisfy { ClassMapper.standard.category(for: $0.label) == $0.category })
    }

    func testPipelineLiftsDetectionsWithDepth() async throws {
        let box = CGRect(x: 0.4, y: 0.4, width: 0.2, height: 0.2)
        let detector = StubDetector(result: [Detection(label: "chair", category: "chair", confidence: 0.9, boundingBox: box, worldCenter: nil, worldSize: nil)])
        let received = DetectionsBox()
        let pipeline = LiveDetectionPipeline(detector: detector) { await received.store($0) }
        let snapshot = FrameSnapshot(
            image: try blankFrame(),
            depth: DepthSamples(width: 10, height: 10, depths: Array(repeating: 1.5, count: 100), confidences: nil),
            camera: CameraGeometry(
                intrinsics: simd_float3x3(columns: (SIMD3(100, 0, 0), SIMD3(0, 100, 0), SIMD3(50, 50, 1))),
                imageSize: SIMD2(100, 100),
                cameraToWorld: matrix_identity_float4x4
            )
        )
        await pipeline.process(snapshot)
        let detections = await received.detections
        let center = try XCTUnwrap(detections.first?.worldCenter)
        XCTAssertEqual(center.z, -1.5, accuracy: 1e-4)
    }
}

private struct StubDetector: ObjectDetecting {
    let result: [Detection]

    func detect(pixelBuffer: CVPixelBufferWrapper) async throws -> [Detection] {
        result
    }
}

private actor DetectionsBox {
    private(set) var detections: [Detection] = []

    func store(_ detections: [Detection]) {
        self.detections = detections
    }
}
