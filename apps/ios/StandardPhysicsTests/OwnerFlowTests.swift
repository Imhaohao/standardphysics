import XCTest
@testable import StandardPhysics

@MainActor
final class ShopSetupStepTests: XCTestCase {
    func testQuestionsComeBeforePhotosAndPhotosBeforeThePushForce() {
        let requests = [
            request("door_opening_force", kind: "number", unit: "lb"),
            request("door_hardware", kind: "photo"),
            request("restroom", kind: "yes_no"),
        ]

        XCTAssertEqual(ShopSetupModel.nextStep(in: requests), .question(requests[2]))
        XCTAssertEqual(ShopSetupModel.nextStep(in: Array(requests.prefix(2))), .photo(requests[1]))
        XCTAssertEqual(ShopSetupModel.nextStep(in: Array(requests.prefix(1))), .pushForce(requests[0]))
    }

    func testOnlyOpenInShopRequestsAreAsked() {
        let requests = [
            request("restroom", kind: "yes_no", status: "answered"),
            request("restroom_turning_space", kind: "photo", status: "not_applicable"),
            request("door_hardware", kind: "photo", status: "skipped"),
            request("finding-1", kind: "number", unit: "in", timing: "follow_up"),
        ]

        XCTAssertEqual(ShopSetupModel.nextStep(in: requests), .measuring)
    }

    func testAnInchMeasurementIsNotThePushForceScreen() {
        XCTAssertEqual(ShopSetupModel.nextStep(in: [request("doorway", kind: "number", unit: "in")]), .measuring)
    }

    func testProgressCountsWhatWasAskedAndLeavesOutWhatANoClosed() {
        let requests = [
            request("restroom", kind: "yes_no", status: "answered"),
            request("inside_doors", kind: "yes_no"),
            request("door_hardware", kind: "photo"),
            request("restroom_turning_space", kind: "photo", status: "not_applicable"),
        ]

        let progress = ShopSetupModel.progress(of: requests, settled: ["inside_doors"])
        XCTAssertEqual(progress.done, 2)
        XCTAssertEqual(progress.total, 3)
    }

    private func request(_ id: String, kind: String, unit: String? = nil, status: String = "open",
                         timing: String = "in_shop") -> OwnerRequest {
        OwnerRequest(id: id, kind: kind, timing: timing, title: id, detail: "", unit: unit, status: status)
    }
}

@MainActor
final class WebBridgeMessageTests: XCTestCase {
    func testEachMessageTheOwnerViewSends() {
        let scan = UUID()
        XCTAssertEqual(WebBridgeMessage(body: ["type": "takePhoto", "requestId": "door_hardware"]),
            .takePhoto(requestID: "door_hardware"))
        XCTAssertEqual(WebBridgeMessage(body: ["type": "addRoom", "scanId": scan.uuidString]), .addRoom(scanID: scan))
        XCTAssertEqual(WebBridgeMessage(body: ["type": "saveReport"]), .saveReport)
        XCTAssertEqual(WebBridgeMessage(body: ["type": "share", "url": "https://standardphysics.app/r/abc", "title": "Tea House"]),
            .share(url: URL(string: "https://standardphysics.app/r/abc")!, title: "Tea House"))
        XCTAssertEqual(WebBridgeMessage(body: ["type": "openLink", "url": "https://www.ada.gov/law-and-regs/design-standards/"]),
            .openLink(URL(string: "https://www.ada.gov/law-and-regs/design-standards/")!))
        XCTAssertEqual(WebBridgeMessage(body: ["type": "stageChanged", "scanId": scan.uuidString, "stage": "fix"]),
            .stageChanged(scanID: scan, stage: "fix"))
        XCTAssertEqual(WebBridgeMessage(body: ["type": "shopDeleted", "scanId": scan.uuidString]), .shopDeleted(scanID: scan))
    }

    func testMalformedMessagesAreDropped() {
        XCTAssertNil(WebBridgeMessage(body: "scanShop"))
        XCTAssertNil(WebBridgeMessage(body: ["type": "launchMissiles"]))
        XCTAssertNil(WebBridgeMessage(body: ["type": "takePhoto"]))
        XCTAssertNil(WebBridgeMessage(body: ["type": "takePhoto", "requestId": "../../api/account"]))
        XCTAssertNil(WebBridgeMessage(body: ["type": "openLink", "url": "javascript:alert(1)"]))
        XCTAssertNil(WebBridgeMessage(body: ["type": "share", "url": "file:///etc/passwd"]))
        XCTAssertNil(WebBridgeMessage(body: ["type": "stageChanged", "scanId": UUID().uuidString]))
        XCTAssertNil(WebBridgeMessage(body: ["type": "shopDeleted"]))
        XCTAssertNil(WebBridgeMessage(body: ["type": "shopDeleted", "scanId": "not-a-shop"]))
    }

    func testTheOwnerViewAndTheExampleLiveWhereTheWebServesThem() {
        let base = URL(string: "https://standardphysics.app")!
        let scan = UUID(uuidString: "2F1D6E1E-8D0B-4C54-9E0A-3C6B1B8F2A10")!

        XCTAssertEqual(WebDestination.owner(scan).url(on: base).absoluteString,
            "https://standardphysics.app/shops/2f1d6e1e-8d0b-4c54-9e0a-3c6b1b8f2a10")
        XCTAssertEqual(WebDestination.example.url(on: base).absoluteString, "https://standardphysics.app/example")
        XCTAssertNil(WebDestination.example.scanID)
    }

    func testTheUserAgentNamesTheAppAndItsBuild() {
        XCTAssertTrue(WorkspaceWebView.userAgentName.hasPrefix("StandardPhysicsApp/"))
    }

    func testAReportFileNameIsReadableAndSafe() {
        XCTAssertEqual(ReportPDF.fileName(for: "Tea House: report/1"), "Tea House report 1.pdf")
        XCTAssertEqual(ReportPDF.fileName(for: "   "), "Standard Physics report.pdf")
    }
}

@MainActor
final class OwnerDetailTests: XCTestCase {
    func testAPhotoIsShrunkToTheLongestSideTheTeamNeeds() throws {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 4_000, height: 3_000)).image { context in
            UIColor.gray.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 4_000, height: 3_000))
        }
        let jpeg = try XCTUnwrap(PhotoEncoding.jpeg(from: image))
        let decoded = try XCTUnwrap(UIImage(data: jpeg))

        XCTAssertEqual(max(decoded.size.width * decoded.scale, decoded.size.height * decoded.scale), 2_400, accuracy: 1)
        XCTAssertEqual(Array(jpeg.prefix(3)), [0xFF, 0xD8, 0xFF])
    }

    func testAGuestDeletionDateReadsWithOrWithoutFractions() {
        XCTAssertNotNil(GuestDeletion.date(from: "2026-10-26T10:00:00Z"))
        XCTAssertNotNil(GuestDeletion.date(from: "2026-10-26T10:00:00.123456+00:00"))
    }

    func testTheWalkWarningLeavesTheSecondsToTheCountdown() {
        XCTAssertFalse(CaptureSessionStore.timeWarningInstruction.contains("30"))
        XCTAssertEqual(FrameRecorder.timeLimit - FrameRecorder.timeWarningLead, 210)
    }

    func testTheFirstWalkCoachesForTwentySeconds() {
        XCTAssertEqual(WalkHistory.openingLine(after: 3), CoverageSnapshot.openingInstruction)
        XCTAssertNotNil(WalkHistory.openingLine(after: 15))
        XCTAssertNil(WalkHistory.openingLine(after: 20))
    }

    func testANewShopIsNamedWhatWasTypedBeforeTheWalk() {
        XCTAssertEqual(ShopName.forWalk(joining: nil, typed: "  Tea House  ", fallback: "My shop"), "Tea House")
    }

    func testANewShopWhoseNameWasClearedTakesTheAccountsShopName() {
        XCTAssertEqual(ShopName.forWalk(joining: nil, typed: "   ", fallback: "g studio"), "g studio")
    }

    func testAWalkThatJoinsAShopKeepsThatShopsName() {
        XCTAssertEqual(ShopName.forWalk(joining: "Corner Books", typed: "Tea House", fallback: "My shop"), "Corner Books")
    }

    func testATypedNameStopsWhereTheServerWouldRefuseIt() {
        XCTAssertEqual(ShopName.limited(String(repeating: "a", count: 200)).count, ShopName.maximumLength)
        let family = "\u{1F468}\u{200D}\u{1F469}\u{200D}\u{1F467}"
        let families = ShopName.limited(String(repeating: family, count: 30))
        XCTAssertEqual(families.unicodeScalars.count, ShopName.maximumLength)
        XCTAssertEqual(families.count, 24, "five scalars each, and none cut in half")
    }

    func testARenamedShopKeepsItsPlaceInTheJourney() throws {
        let json = #"{"scan_id": "2F1D6E1E-8D0B-4C54-9E0A-3C6B1B8F2A10", "shop_name": "Tea House", "stage": "results", "next_step": {"kind": "results", "title": "Your results are ready", "count": 3}, "tools_unlocked": true}"#
        let journey = try JSONDecoder().decode(Journey.self, from: Data(json.utf8))
        let renamed = journey.named("Tea House Annex")

        XCTAssertEqual(renamed.shopName, "Tea House Annex")
        XCTAssertEqual(renamed.scanID, journey.scanID)
        XCTAssertEqual(renamed.nextStep, journey.nextStep)
    }

    func testAJourneyBeforeResultsKeepsTheOwnerOnThePhone() throws {
        let json = #"{"scan_id": "2F1D6E1E-8D0B-4C54-9E0A-3C6B1B8F2A10", "shop_name": "Tea House", "stage": "fill_in_the_gaps", "next_step": {"kind": "photos", "title": "Take 2 more photos", "count": 2}, "tools_unlocked": false}"#
        let journey = try JSONDecoder().decode(Journey.self, from: Data(json.utf8))

        XCTAssertTrue(journey.isBeforeResults)
        XCTAssertEqual(journey.nextStep.count, 2)
    }
}

@MainActor
final class BackgroundPhotoTests: XCTestCase {
    private let jpeg = Data([0xFF, 0xD8, 0xFF, 0xE0])
    private let doorHandle = photoRequest("door_hardware")
    private let floor = photoRequest("floor_surface")

    func testTakingAPhotoMovesOnBeforeItHasSent() async throws {
        let server = PhotoServer(.hold)
        let setup = flow([doorHandle, floor], server: server)

        setup.sendPhoto(jpeg)

        XCTAssertEqual(setup.step, .photo(floor))
        XCTAssertEqual(setup.progress.done, 1)
        XCTAssertEqual(setup.outbox.count, 1)
        try await waitUntil { server.heldCount == 1 }
        server.letOneThrough()
        try await waitUntil { setup.outbox.count == 0 }
        XCTAssertEqual(setup.step, .photo(floor))
        XCTAssertEqual(server.tries.map(\.requestID), ["door_hardware"])
    }

    func testTheCountIsEveryPhotoStillOnItsWay() async throws {
        let server = PhotoServer(.hold, .hold)
        let outbox = PhotoOutbox(wait: server.wait, upload: server.receive)

        outbox.send(photo("door_hardware")) { _ in XCTFail("no photo failed") }
        outbox.send(photo("floor_surface")) { _ in XCTFail("no photo failed") }

        XCTAssertEqual(outbox.count, 2)
        try await waitUntil { server.heldCount == 2 }
        server.letOneThrough()
        try await waitUntil { outbox.count == 1 }
        server.letOneThrough()
        try await waitUntil { outbox.count == 0 }
    }

    func testAFailedSendIsTriedAgainUntilItGoesThrough() async throws {
        let server = PhotoServer(.refuse, .refuse, .take)
        let outbox = PhotoOutbox(wait: server.wait, upload: server.receive)
        var failures = 0

        outbox.send(photo("door_hardware")) { _ in failures += 1 }
        try await waitUntil { outbox.count == 0 }

        XCTAssertEqual(server.tries.map(\.jpeg), [jpeg, jpeg, jpeg], "every try sends the same photo")
        XCTAssertEqual(server.waits, PhotoOutbox.retryWaits)
        XCTAssertEqual(failures, 0)
    }

    func testAPhotoThatNeverSendsIsAskedForAgain() async throws {
        let server = PhotoServer(.refuse, .refuse, .refuse)
        let setup = flow([doorHandle], server: server)

        setup.sendPhoto(jpeg)
        XCTAssertEqual(setup.step, .measuring)
        try await waitUntil { setup.outbox.count == 0 }

        XCTAssertEqual(server.tries.count, 3)
        XCTAssertEqual(server.waits, PhotoOutbox.retryWaits)
        XCTAssertEqual(setup.step, .photo(doorHandle))
        XCTAssertEqual(setup.problem, ShopSetupModel.unsentPhotoProblem)
        XCTAssertEqual(setup.progress.done, 0)
    }

    func testAPhotoThatFailsMidStepComesBackOnceThatStepIsDone() async throws {
        let server = PhotoServer(.refuse, .refuse, .refuse)
        let setup = flow([doorHandle, floor], server: server)

        setup.sendPhoto(jpeg)
        try await waitUntil { setup.outbox.count == 0 }
        XCTAssertEqual(setup.step, .photo(floor), "the screen never changes under the owner")
        XCTAssertNil(setup.problem)

        setup.sendPhoto(jpeg)
        XCTAssertEqual(setup.step, .photo(doorHandle))
        XCTAssertEqual(setup.problem, ShopSetupModel.unsentPhotoProblem)
        try await waitUntil { setup.outbox.count == 0 }
    }

    private func flow(_ requests: [OwnerRequest], server: PhotoServer) -> ShopSetupModel {
        ShopSetupModel(scanID: UUID(), requests: requests,
            outbox: PhotoOutbox(wait: server.wait, upload: server.receive))
    }

    private func photo(_ requestID: String) -> PhotoOutbox.Photo {
        PhotoOutbox.Photo(scanID: UUID(), requestID: requestID, jpeg: jpeg)
    }
}

/// Stands in for the server in the photo tests. Each try takes the next
/// answer in line, and a held try waits until the test lets it through.
@MainActor
private final class PhotoServer {
    enum Answer { case take, refuse, hold }

    private var answers: [Answer]
    private var held: [CheckedContinuation<Void, Never>] = []
    private(set) var tries: [PhotoOutbox.Photo] = []
    private(set) var waits: [Duration] = []

    var heldCount: Int { held.count }

    init(_ answers: Answer...) { self.answers = answers }

    func receive(_ photo: PhotoOutbox.Photo) async throws {
        tries.append(photo)
        switch answers.isEmpty ? .take : answers.removeFirst() {
        case .take: return
        case .refuse: throw OwnerAPIError.unreachable
        case .hold: await withCheckedContinuation { held.append($0) }
        }
    }

    func wait(_ duration: Duration) async throws {
        waits.append(duration)
    }

    func letOneThrough() {
        held.removeFirst().resume()
    }
}

private func photoRequest(_ id: String) -> OwnerRequest {
    OwnerRequest(id: id, kind: "photo", timing: "in_shop", title: id, detail: "", unit: nil, status: "open")
}
