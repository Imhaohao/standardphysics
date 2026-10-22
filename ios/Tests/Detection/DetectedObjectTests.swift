import XCTest
import simd
@testable import StandardPhysics

enum RepoFixtures {
    static var root: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
    }

    static func room(_ name: String = "test1") throws -> Data {
        try Data(contentsOf: root.appending(path: "fixtures/phone/\(name)/room.json"))
    }

    /// test1's floor sits at this world Y; a fridge standing on it in the empty corner by the door.
    static let test1FloorLevel: Float = -1.2488208
    static let test1Fridge = SIMD3<Float>(-4.9, test1FloorLevel + 0.85, -1.0)

    static func track(_ category: String, at center: SIMD3<Float>, size: SIMD3<Float> = SIMD3(0.7, 1.7, 0.7)) -> DetectionTrack {
        DetectionTrack(category: category, label: category, center: center, size: size, hits: 4, confidenceSum: 3.2)
    }
}

final class DetectedObjectTests: XCTestCase {
    func testFloorLevelMatchesTheEngine() throws {
        let room = try XCTUnwrap(CapturedRoomGeometry(capturedRoomJSON: RepoFixtures.room()))
        XCTAssertEqual(room.floorLevel, RepoFixtures.test1FloorLevel, accuracy: 1e-5)
        XCTAssertEqual(room.objects.count, 16)
        XCTAssertEqual(Set(room.objects.map(\.category)), ["table", "chair", "storage"])
    }

    func testFloorFallsBackToTheLowestWallThenObject() throws {
        let walls = Data(#"{"walls":[{"dimensions":[2,2.5,0.1],"transform":[1,0,0,0,0,1,0,0,0,0,1,0,0,0.25,0,1]}]}"#.utf8)
        XCTAssertEqual(try XCTUnwrap(CapturedRoomGeometry(capturedRoomJSON: walls)).floorLevel, -1, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(CapturedRoomGeometry(capturedRoomJSON: Data(#"{"walls":[]}"#.utf8))).floorLevel, 0)
    }

    func testObjectsAreFloorRelativeWithTheirTopHeight() throws {
        let room = try XCTUnwrap(CapturedRoomGeometry(capturedRoomJSON: RepoFixtures.room()))
        let finished = DetectedObjects.finished(tracks: [RepoFixtures.track("refrigerator", at: RepoFixtures.test1Fridge)], room: room) { "fridge-1" }
        let fridge = try XCTUnwrap(finished.objects.first)
        XCTAssertEqual(fridge.id, "fridge-1")
        XCTAssertEqual(fridge.center.y, 0.85, accuracy: 1e-4)
        XCTAssertEqual(fridge.center.x, -4.9, accuracy: 1e-4)
        XCTAssertEqual(fridge.topHeight, 1.7, accuracy: 1e-4)
        XCTAssertEqual(fridge.yaw, 0)
        XCTAssertEqual(fridge.confidence, 0.8, accuracy: 1e-5)
    }

    func testRoomPlanStaysTheSourceOfTruthForWhatItAlreadyFound() throws {
        let room = try XCTUnwrap(CapturedRoomGeometry(capturedRoomJSON: RepoFixtures.room()))
        let onTheTable = SIMD3<Float>(-5.0, -0.86, 1.98)
        let diningTable = RepoFixtures.track("table", at: onTheTable + SIMD3(0.3, 0, 0.2), size: SIMD3(1.9, 0.8, 0.9))
        let fridgeByTheTable = RepoFixtures.track("refrigerator", at: onTheTable)
        let finished = DetectedObjects.finished(tracks: [diningTable, fridgeByTheTable], room: room)
        XCTAssertEqual(finished.kept.map(\.category), ["refrigerator"], "only a compatible RoomPlan object hides a detection")
    }

    func testDuplicatesNeedACompatibleCategoryAndOverlap() throws {
        let planned = CapturedRoomGeometry.PlannedObject(category: "sofa", transform: matrix_identity_float4x4, dimensions: SIMD3(2, 0.8, 1))
        let room = CapturedRoomGeometry(floorLevel: 0, objects: [planned])
        let halfOverlapping = RepoFixtures.track("sofa", at: SIMD3(1, 0.4, 0), size: SIMD3(2, 0.8, 1))
        XCTAssertEqual(DetectedObjects.planIoU(halfOverlapping, planned), 1.0 / 3.0, accuracy: 1e-5)
        XCTAssertTrue(DetectedObjects.isAlreadyPlanned(halfOverlapping, in: room))
        XCTAssertTrue(DetectedObjects.isAlreadyPlanned(RepoFixtures.track("chair", at: .zero), in: room))
        XCTAssertFalse(DetectedObjects.isAlreadyPlanned(RepoFixtures.track("television", at: .zero), in: room))
        XCTAssertFalse(DetectedObjects.isAlreadyPlanned(RepoFixtures.track("sofa", at: SIMD3(3, 0.4, 0)), in: room))
    }

    func testObservationHasTheShapeTheServerTurnsIntoAnObject() throws {
        let object = DetectedObject(
            id: "detector-1", category: "refrigerator", label: "refrigerator",
            center: ScenePoint(x: 1, y: 0.85, z: 2), size: ScenePoint(x: 0.7, y: 1.7, z: 0.7), confidence: 0.8, hits: 4
        )
        let data = try JSONEncoder().encode(object)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["id"] as? String, "detector-1")
        XCTAssertEqual(json["category"] as? String, "refrigerator")
        XCTAssertEqual((json["center"] as? [String: Double])?["y"], 0.85)
        XCTAssertEqual((json["size"] as? [String: Double])?["y"], 1.7)
        XCTAssertEqual(json["top_height"] as? Double ?? 0, 1.7, accuracy: 1e-9)
        XCTAssertNotNil(object.observation)
    }

    func testSidecarLivesNextToItsRoomAndToleratesAbsence() throws {
        XCTAssertEqual(DetectedObjectFile.path(forRoomFile: "rooms/3.json"), "rooms/3.detections.json")
        XCTAssertEqual(ScanFiles.detections(0), "rooms/0.detections.json")
        let missing = FileManager.default.temporaryDirectory.appending(path: "\(UUID().uuidString)/rooms/0.json")
        XCTAssertEqual(DetectedObjectFile.objects(forRoomAt: missing), [])
    }

    func testEveryMappedCategoryExistsInTheRulesCatalog() throws {
        let data = try Data(contentsOf: RepoFixtures.root.appending(path: "rules/metrics.json"))
        let catalog = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let categories = try XCTUnwrap(catalog["object_categories"] as? [[String: Any]]).compactMap { $0["id"] as? String }
        XCTAssertTrue(ClassMapper.engineCategories.isSubset(of: Set(categories)), "\(ClassMapper.engineCategories.subtracting(categories))")
        XCTAssertEqual(ClassMapper.standard.category(for: "microwave"), "microwave")
        XCTAssertEqual(ClassMapper.standard.category(for: "refrigerator"), "refrigerator")
    }
}
