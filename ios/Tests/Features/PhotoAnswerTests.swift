import XCTest
@testable import StandardPhysics

@MainActor
final class PhotoAnswerTests: XCTestCase {
    private let photoAsk = FindingAsk(metric: "sign.braille_present", prompt: "Is there a Braille sign?", valueType: .boolean, photo: true)

    private func makeModel(_ library: FakeScanLibrary) -> (AppModel, ScanReport) {
        let report = ServerReports.scanReport(scan: LibraryFixtures.scan(), report: LibraryFixtures.report(), sceneJSON: nil)
        let model = AppModel(
            capture: PreviewCaptureController(storedScans: []), processor: PreviewScanProcessor(),
            account: AccountModel(service: nil, state: .signedIn(email: "a@b.co")), library: library, reports: [report]
        )
        return (model, report)
    }

    func testAReadablePhotoAnswersTheQuestion() async {
        let library = FakeScanLibrary()
        library.readPhotosAs(.bool(true))
        let (model, report) = makeModel(library)
        let question = OwnerQuestion(subjectID: "door-1", ask: photoAsk)
        XCTAssertTrue(model.canAnswerWithPhoto(question, inReport: report.scanID))

        let outcome = await model.answerWithPhoto(question, jpeg: Data([0xFF, 0xD8]), inReport: report.scanID)

        XCTAssertEqual(outcome, .answered)
        XCTAssertEqual(library.uploadedPhotos, [Data([0xFF, 0xD8])])
        XCTAssertEqual(model.report(id: report.scanID)?.findings.map(\.status), [.pass])
        let stored = model.report(id: report.scanID)?.answers.first
        XCTAssertEqual(stored?.value, .bool(true))
        XCTAssertEqual(stored?.isFromPhoto, true)
        XCTAssertTrue(OwnerQuestions.updates(for: [stored!], clearing: nil).isEmpty, "photo answers are not re-sent as typed ones")
    }

    func testAnUnclearPhotoLeavesTheQuestionOpen() async {
        let library = FakeScanLibrary()
        let (model, report) = makeModel(library)
        let outcome = await model.answerWithPhoto(OwnerQuestion(subjectID: "door-1", ask: photoAsk), jpeg: Data([1]), inReport: report.scanID)
        XCTAssertEqual(outcome, .unclear)
        XCTAssertTrue(model.report(id: report.scanID)?.answers.isEmpty ?? false)
        XCTAssertNotNil(PhotoAnswerCopy.message(for: outcome, isReading: false))
    }

    func testAServerThatCantReadPhotosHidesTheOptionForTheSession() async {
        let library = FakeScanLibrary()
        library.failNextCalls(with: .conflict(message: nil))
        let (model, report) = makeModel(library)
        let question = OwnerQuestion(subjectID: "door-1", ask: photoAsk)

        let outcome = await model.answerWithPhoto(question, jpeg: Data([1]), inReport: report.scanID)

        XCTAssertEqual(outcome, .unavailable)
        XCTAssertFalse(model.canAnswerWithPhoto(question, inReport: report.scanID))
        XCTAssertNil(model.notice)
    }

    func testPhotosAreOfferedOnlyWhereTheRuleAsksForOne() {
        let (model, report) = makeModel(FakeScanLibrary())
        XCTAssertFalse(model.canAnswerWithPhoto(OwnerQuestion(subjectID: "door-1", ask: LibraryFixtures.ask), inReport: report.scanID))
        let phoneOnly = AppModel(capture: PreviewCaptureController(storedScans: []), processor: PreviewScanProcessor(), library: FakeScanLibrary(), reports: [SampleData.completedReport])
        XCTAssertFalse(phoneOnly.canAnswerWithPhoto(OwnerQuestion(subjectID: "door-1", ask: photoAsk), inReport: SampleData.completedReport.scanID))
    }

    func testPhotoAnswerRouteAndBody() throws {
        let route = APIRoutes.photoAnswer(scanID: "s1", body: PhotoAnswerRequest(subjectID: "door-1", metric: "m", artifactID: "a1"))
        XCTAssertEqual(route.method, .post)
        XCTAssertEqual(route.path, "/v1/scans/s1/photo-answers")
        let body = try WireCoding.encoder().encode(PhotoAnswerRequest(subjectID: "door-1", metric: "m", artifactID: "a1"))
        XCTAssertEqual(String(data: body, encoding: .utf8), #"{"artifact_id":"a1","metric":"m","subject_id":"door-1"}"#)
    }

    func testServerAnswersKeepTheirSource() throws {
        let json = #"[{"subject_id":"d","metric":"m","value":true,"source":"photo","confidence":0.92,"photo_artifact_id":"a1","answered_at":"2026-10-19T10:00:00Z"}]"#
        let answers = try WireCoding.decoder().decode([ServerAnswer].self, from: Data(json.utf8))
        XCTAssertEqual(answers.first?.photoArtifactID, "a1")
        XCTAssertEqual(answers.first?.asOwnerAnswer?.isFromPhoto, true)
    }
}

final class PhotoUploaderTests: XCTestCase {
    func testAPhotoGoesUpInPartsAndReturnsTheArtifact() async throws {
        let api = FakeUploadAPI()
        let storage = ScriptedTransport([
            .success(HTTPResponse(status: 200, headers: ["etag": "\"1\""], body: Data())),
            .success(HTTPResponse(status: 200, headers: ["etag": "\"2\""], body: Data())),
        ])
        let uploader = PhotoUploader(
            api: api, storage: storage, policy: StorageHostPolicy(allowedHosts: ["r2.test"], allowsLocalHTTP: false), partSize: 4
        )
        let jpeg = Data([1, 2, 3, 4, 5, 6])

        let artifactID = try await uploader.upload(jpeg: jpeg, scanID: "s1")

        XCTAssertEqual(artifactID, "a1")
        XCTAssertEqual(api.createCalls.first?.body.kind, "photo")
        XCTAssertEqual(api.createCalls.first?.body.contentType, "image/jpeg")
        XCTAssertEqual(api.presignCalls, [[1, 2]])
        XCTAssertEqual(storage.requests.map(\.httpBody), [Data([1, 2, 3, 4]), Data([5, 6])])
        XCTAssertEqual(api.completeCalls.first?.sha256, PhotoUploader.sha256Hex(jpeg))
    }
}
