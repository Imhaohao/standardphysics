import XCTest
@testable import StandardPhysics

final class UploadLedgerTests: XCTestCase {
    private var directory: URL!
    private var ledgerURL: URL { directory.appendingPathComponent("ledger.json") }

    override func setUpWithError() throws { directory = try makeTemporaryDirectory() }
    override func tearDownWithError() throws { try? FileManager.default.removeItem(at: directory) }

    private func makeRecord(name: String = "room-1.json") -> UploadRecord {
        UploadRecord(
            id: UUID(), scanID: "scan-1", fileName: name, kind: "room", contentType: "application/json", sizeBytes: 2500,
            sha256: "abc123", enqueuedAt: fixedNow, state: .queued, multipart: nil
        )
    }

    private func makeMultipart() -> MultipartSession {
        let parts = (1...3).map {
            UploadPart(number: $0, url: URL(string: "https://r2.test/p\($0)")!, expiresAt: fixedNow.addingTimeInterval(600))
        }
        return MultipartSession(uploadID: "up-1", partSize: 1000, parts: parts)
    }

    func testRecordsSurviveRelaunchWithPartsEtagsAndExpiry() async throws {
        let first = UploadLedger(fileURL: ledgerURL)
        let record = makeRecord()
        try await first.insert(record)
        let multipart = makeMultipart()
        try await first.update(record.id) {
            $0.multipart = multipart
            $0.state = .uploading
            $0.multipart?.updatePart(2) { $0.etag = "\"e2\"" }
        }

        let relaunched = UploadLedger(fileURL: ledgerURL)
        let found = await relaunched.record(record.id)
        let restored = try XCTUnwrap(found)
        XCTAssertEqual(restored.state, .uploading)
        XCTAssertEqual(restored.multipart?.uploadID, "up-1")
        XCTAssertEqual(restored.multipart?.parts.map(\.etag), [nil, "\"e2\"", nil])
        XCTAssertEqual(restored.multipart?.parts[0].expiresAt, fixedNow.addingTimeInterval(600))
        XCTAssertEqual(restored.multipart?.parts[0].url?.absoluteString, "https://r2.test/p1")
        XCTAssertEqual(restored.sha256, "abc123")
    }

    func testFailedStateKeepsItsMessageAcrossRelaunch() async throws {
        let ledger = UploadLedger(fileURL: ledgerURL)
        let record = makeRecord()
        try await ledger.insert(record)
        try await ledger.update(record.id) { $0.state = .failed(message: "Disk full") }
        let restored = await UploadLedger(fileURL: ledgerURL).record(record.id)
        XCTAssertEqual(restored?.state.failureMessage, "Disk full")
    }

    func testWritesLeaveNoTemporaryFilesBehind() async throws {
        let ledger = UploadLedger(fileURL: ledgerURL)
        for index in 0..<5 { try await ledger.insert(makeRecord(name: "r\(index).json")) }
        let files = try FileManager.default.contentsOfDirectory(atPath: directory.path)
        XCTAssertEqual(files, ["ledger.json"])
    }

    func testRemoveDeletesRecordsFromDisk() async throws {
        let ledger = UploadLedger(fileURL: ledgerURL)
        let keep = makeRecord(name: "keep.json")
        let drop = makeRecord(name: "drop.json")
        try await ledger.insert(keep)
        try await ledger.insert(drop)
        try await ledger.remove([drop.id])
        let restored = await UploadLedger(fileURL: ledgerURL).all()
        XCTAssertEqual(restored.map(\.id), [keep.id])
    }

    func testUnreadableLedgerIsSetAsideAndLedgerStartsEmpty() async throws {
        try Data("not json".utf8).write(to: ledgerURL)
        let ledger = UploadLedger(fileURL: ledgerURL)
        let records = await ledger.all()
        XCTAssertTrue(records.isEmpty)
        let names = try FileManager.default.contentsOfDirectory(atPath: directory.path)
        XCTAssertTrue(names.contains { $0.contains("unreadable") })
        try await ledger.insert(makeRecord())
        let restored = await UploadLedger(fileURL: ledgerURL).all()
        XCTAssertEqual(restored.count, 1)
    }

    func testPartExpiryUsesSafetySkew() {
        let part = UploadPart(number: 1, url: URL(string: "https://r2.test")!, expiresAt: fixedNow.addingTimeInterval(100))
        XCTAssertTrue(part.needsFreshURL(at: fixedNow, skew: 120))
        XCTAssertFalse(part.needsFreshURL(at: fixedNow, skew: 60))
        XCTAssertTrue(UploadPart(number: 2).needsFreshURL(at: fixedNow, skew: 0), "no URL yet")
    }

    func testUploadsFolderIsExcludedFromBackup() async throws {
        let directory = try makeTemporaryDirectory().appendingPathComponent("Uploads")
        let ledger = UploadLedger(fileURL: directory.appendingPathComponent("upload-ledger.json"))
        try await ledger.insert(UploadRecord(
            id: UUID(), scanID: "s", fileName: "f", kind: "mesh", contentType: "x", sizeBytes: 1, sha256: "h",
            enqueuedAt: fixedNow, state: .queued, multipart: nil
        ))
        XCTAssertEqual(try directory.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
    }
}
