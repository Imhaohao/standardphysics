import CoreGraphics
import XCTest
import simd
@testable import StandardPhysics

private func makeCamera(at position: SIMD3<Float> = .zero) -> CameraGeometry {
    var toWorld = matrix_identity_float4x4
    toWorld.columns.3 = SIMD4(position, 1)
    return CameraGeometry(
        intrinsics: simd_float3x3(columns: (SIMD3(1000, 0, 0), SIMD3(0, 1000, 0), SIMD3(960, 720, 1))),
        imageSize: SIMD2(1920, 1440),
        cameraToWorld: toWorld
    )
}

private func planned(
    _ category: String, center: SIMD3<Float>, size: SIMD3<Float> = SIMD3(1, 1, 1), id: String = "OBJ"
) -> CapturedRoomGeometry.PlannedObject {
    var transform = matrix_identity_float4x4
    transform.columns.3 = SIMD4(center, 1)
    return CapturedRoomGeometry.PlannedObject(category: category, transform: transform, dimensions: size, identifier: id)
}

final class RelabelSelectionTests: XCTestCase {
    func testDoubtfulCategoriesAndCounterHeightsAreChecked() {
        let room = CapturedRoomGeometry(floorLevel: 0, objects: [
            planned("toilet", center: SIMD3(0, 0.2, 0), size: SIMD3(0.4, 0.4, 0.6), id: "low-toilet"),
            planned("refrigerator", center: SIMD3(0, 0.45, 0), size: SIMD3(0.6, 0.9, 0.6), id: "counter-height-fridge"),
            planned("refrigerator", center: SIMD3(0, 0.9, 0), size: SIMD3(0.7, 1.8, 0.7), id: "tall-fridge"),
            planned("bed", center: SIMD3(0, 0.25, 0), size: SIMD3(2, 0.5, 1), id: "bench-like-bed"),
            planned("storage", center: SIMD3(0, 0.48, 0), size: SIMD3(1.8, 0.965, 0.6), id: "counter"),
            planned("storage", center: SIMD3(0, 0.48, 0), size: SIMD3(1.8, 0.965, 0.6), id: ""),
        ])
        let ids = RelabelSelection.candidates(in: room).map(\.identifier)
        XCTAssertEqual(ids, ["counter", "counter-height-fridge", "bench-like-bed"])
    }

    func testTopHeightIsMeasuredFromTheFloor() {
        let object = planned("table", center: SIMD3(0, -0.8, 0), size: SIMD3(1, 0.9, 1))
        XCTAssertEqual(RelabelSelection.topHeight(of: object, floorLevel: -1.25), 0.9, accuracy: 1e-5)
    }

    func testARoomSendsAtMostTwentyCrops() {
        let chairs = (0..<30).map { planned("chair", center: SIMD3(Float($0), 0.45, 0), id: "chair-\($0)") }
        XCTAssertEqual(RelabelSelection.candidates(in: CapturedRoomGeometry(floorLevel: 0, objects: chairs)).count, 20)
    }

    func testRoomPlanIdentifiersAreReadAsTheEngineSeesThem() throws {
        let room = try XCTUnwrap(CapturedRoomGeometry(capturedRoomJSON: RepoFixtures.room()))
        XCTAssertTrue(room.objects.contains { $0.identifier == "95D36655-79F7-4C78-A624-8DC8B29FDB7E" })
        XCTAssertEqual(RelabelSelection.candidates(in: room).count, 16)
    }
}

final class BoxProjectionTests: XCTestCase {
    func testProjectionUndoesTheDepthLifter() throws {
        let camera = makeCamera(at: SIMD3(0.3, 1.2, -0.5))
        let normalized = CGPoint(x: 0.7, y: 0.25)
        let world = DepthLifter.worldPoint(normalized: normalized, distance: 2.5, camera: camera)
        let pixel = try XCTUnwrap(BoxProjection.project(world, camera: camera))
        XCTAssertEqual(pixel.x, 0.7 * 1920, accuracy: 0.05)
        XCTAssertEqual(pixel.y, 0.25 * 1440, accuracy: 0.05)
    }

    func testPointsBehindTheCameraDoNotProject() {
        XCTAssertNil(BoxProjection.project(SIMD3(0, 0, 1), camera: makeCamera()))
    }

    func testABoxAheadCoversTheMiddleOfTheImage() throws {
        let box = planned("storage", center: SIMD3(0, 0, -3))
        let rect = try XCTUnwrap(BoxProjection.visibleRect(transform: box.transform, dimensions: box.dimensions, camera: makeCamera()))
        XCTAssertEqual(rect.minX, 760, accuracy: 0.5)
        XCTAssertEqual(rect.maxX, 1160, accuracy: 0.5)
        XCTAssertEqual(rect.midY, 720, accuracy: 0.5)
    }

    func testABoxPartlyOutOfFrameIsNotInView() {
        let box = planned("storage", center: SIMD3(-3, 0, -3))
        XCTAssertNil(BoxProjection.visibleRect(transform: box.transform, dimensions: box.dimensions, camera: makeCamera()))
    }
}

final class RelabelCropperTests: XCTestCase {
    func testTheFrameWhereTheBoxIsLargestAndWhollyVisibleWins() throws {
        let box = planned("storage", center: SIMD3(0, 0, -3))
        let cameras = [makeCamera(at: SIMD3(0, 0, 2)), makeCamera(at: SIMD3(5, 0, 1.5)), makeCamera(), makeCamera(at: SIMD3(0.2, 0, 1))]
        let choice = try XCTUnwrap(RelabelCropper.bestFrame(for: box, among: cameras))
        XCTAssertEqual(choice.frameIndex, 2, "the closest camera that still sees the whole box")
        XCTAssertEqual(choice.rect.width, 480, accuracy: 0.5, "padded by a tenth on each side")
    }

    func testNoFrameMeansNoCrop() {
        let box = planned("storage", center: SIMD3(0, 0, 3))
        XCTAssertNil(RelabelCropper.bestFrame(for: box, among: [makeCamera()]))
    }

    func testPaddingStaysInsideTheImage() {
        let rect = RelabelCropper.padded(CGRect(x: 0, y: 0, width: 100, height: 100), imageSize: SIMD2(1920, 1440))
        XCTAssertEqual(rect, CGRect(x: 0, y: 0, width: 110, height: 110))
    }
}

final class KeyframeRingTests: XCTestCase {
    func testAFullRingThinsOutAndSamplesLessOften() {
        var ring = KeyframeRing<Int>(capacity: 4, startInterval: 1)
        for frame in 0..<4 { ring.append(frame) }
        XCTAssertEqual(ring.frames, [0, 1, 2, 3])
        ring.append(4)
        XCTAssertEqual(ring.frames, [0, 2, 4])
        XCTAssertEqual(ring.interval, 2)
    }

    func testSamplingWaitsForTheInterval() {
        var ring = KeyframeRing<Int>(capacity: 4, startInterval: 1)
        XCTAssertTrue(ring.isDue(at: 10))
        ring.markSampled(at: 10)
        XCTAssertFalse(ring.isDue(at: 10.5))
        XCTAssertTrue(ring.isDue(at: 11))
        ring.reset()
        XCTAssertTrue(ring.isDue(at: 10.1))
        XCTAssertEqual(ring.interval, 1)
    }
}

private final class FakeCropUploader: CropUploading, @unchecked Sendable {
    private let state = Locked<[Data]>([])
    var uploads: [Data] { state.read { $0 } }

    func uploadCrop(jpeg: Data, scanID: String) async throws -> String {
        state.write { $0.append(jpeg) }
        return "artifact-\(jpeg.count)"
    }
}

final class RelabelCropFileTests: XCTestCase {
    private var directory: URL!

    override func setUp() async throws {
        directory = try makeTemporaryDirectory()
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: directory)
    }

    func testFilesSitNextToTheirRoom() {
        XCTAssertEqual(RelabelCropFile.path(forRoomFile: "rooms/0.json"), "rooms/0.relabel.json")
        XCTAssertEqual(RelabelCropFile.cropPath(forRoomFile: "0.json", index: 2), "0.relabel-2.jpg")
    }

    func testOnlyUploadedCropsBecomeObservations() {
        var file = RelabelCropFile(entries: [
            .init(objectID: "A", cropFile: "0.relabel-0.jpg"),
            .init(objectID: "B", cropFile: "0.relabel-1.jpg"),
        ])
        file.record(artifactIDs: ["B": "art-b"])
        XCTAssertEqual(file.pendingUploads.map(\.objectID), ["A"])
        XCTAssertEqual(file.observations, [.object([
            "id": .string("relabel-B"), "relabel_object_id": .string("B"), "crop_artifact_id": .string("art-b"),
        ])])
    }

    func testPendingCropsUploadOnceAndTheirIdsAreKept() async throws {
        let roomURL = directory.appending(path: "0.json")
        try Data("{}".utf8).write(to: roomURL)
        try Data([1, 2, 3]).write(to: directory.appending(path: "0.relabel-0.jpg"))
        try Data([1, 2, 3, 4, 5]).write(to: directory.appending(path: "0.relabel-1.jpg"))
        let file = RelabelCropFile(entries: [
            .init(objectID: "A", cropFile: "0.relabel-0.jpg"),
            .init(objectID: "B", cropFile: "0.relabel-1.jpg"),
        ])
        try file.encoded().write(to: RelabelCropFile.url(forRoomAt: roomURL))
        let uploader = FakeCropUploader()

        let first = await RelabelCropUploads.uploadPending(forRoomAt: roomURL, scanID: "s1", uploader: uploader, budget: .seconds(5))
        let second = await RelabelCropUploads.uploadPending(forRoomAt: roomURL, scanID: "s1", uploader: uploader, budget: .seconds(5))

        XCTAssertEqual(first, 2)
        XCTAssertEqual(second, 0)
        XCTAssertEqual(uploader.uploads.count, 2)
        let saved = try XCTUnwrap(RelabelCropFile.load(forRoomAt: roomURL))
        XCTAssertEqual(saved.entries.map(\.artifactID), ["artifact-3", "artifact-5"])
    }

    func testBatchesSplitEvenly() {
        XCTAssertEqual(RelabelCropUploads.batches(of: Array(1...5), size: 2), [[1, 2], [3, 4], [5]])
        XCTAssertEqual(RelabelCropUploads.batches(of: [Int](), size: 4), [])
    }
}
