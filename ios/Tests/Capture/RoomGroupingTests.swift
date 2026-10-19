import XCTest
@testable import StandardPhysics

final class RoomGroupingTests: XCTestCase {
    private actor MergeLog {
        var attempts: [[Int]] = []
        func record(_ rooms: [Int]) { attempts.append(rooms) }
    }

    func testOneFrameMergesEverythingInOneAttempt() async {
        let log = MergeLog()
        let groups = await RoomGrouping.group(frames: [0, 0, 0]) { rooms -> String? in
            await log.record(rooms)
            return "merged \(rooms)"
        }
        XCTAssertEqual(groups.map(\.rooms), [[0, 1, 2]])
        XCTAssertEqual(groups.first?.merged, "merged [0, 1, 2]")
        let attempts = await log.attempts
        XCTAssertEqual(attempts, [[0, 1, 2]])
    }

    func testRoomsFromDifferentFramesAreNeverMergedTogether() async {
        let log = MergeLog()
        let groups = await RoomGrouping.group(frames: [0, 0, 1, 0, 1]) { rooms -> Int? in
            await log.record(rooms)
            return rooms.count
        }
        XCTAssertEqual(groups.map(\.rooms), [[0, 1, 3], [2, 4]])
        let attempts = await log.attempts
        XCTAssertEqual(attempts, [[0, 1, 3], [2, 4]])
    }

    func testSingleRoomFrameIsExportedAlone() async {
        let groups = await RoomGrouping.group(frames: [0, 1]) { _ -> Int? in
            XCTFail("a single room needs no merge")
            return nil
        }
        XCTAssertEqual(groups.map(\.rooms), [[0], [1]])
        XCTAssertTrue(groups.allSatisfy { $0.merged == nil })
    }

    func testFailedMergeFallsBackToGreedyGroups() async {
        let groups = await RoomGrouping.group(frames: [0, 0, 0, 0]) { rooms -> [Int]? in
            rooms.contains(1) && rooms.contains(2) ? nil : rooms
        }
        XCTAssertEqual(groups.map(\.rooms), [[0, 1], [2, 3]])
        XCTAssertEqual(groups.map(\.merged), [[0, 1], [2, 3]])
    }

    func testNoRoomsNoGroups() async {
        let groups = await RoomGrouping.group(frames: []) { _ -> Int? in 1 }
        XCTAssertTrue(groups.isEmpty)
    }

    func testFrameLogTracksFreshRunsAndRelocalization() {
        var log = FrameLog()
        log.recordRoom(0)
        log.worldMapFrame = log.current
        log.beginNewFrame()
        XCTAssertEqual(log.current, 1)
        log.recordRoom(1)
        log.rejoinWorldMapFrame()
        XCTAssertEqual(log.current, 0)
        log.recordRoom(2)
        log.beginNewFrame()
        XCTAssertEqual(log.current, 2)
        log.recordRoom(1)
        XCTAssertEqual(log.roomFrames, [0, 2, 0])
        XCTAssertEqual(log.frame(ofRoom: 7), 0)
    }

    func testFrameLogPadsSkippedRooms() {
        var log = FrameLog(current: 3)
        log.recordRoom(2)
        XCTAssertEqual(log.roomFrames, [3, 3, 3])
    }
}
