import CryptoKit
import XCTest
@testable import StandardPhysics

final class PartSlicerTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws { directory = try makeTemporaryDirectory() }
    override func tearDownWithError() throws { try? FileManager.default.removeItem(at: directory) }

    private func sha256(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    func testPartCountAndLengthsCoverFileExactly() {
        XCTAssertEqual(PartSlicer.partCount(fileSize: 10_000, partSize: 4096), 3)
        XCTAssertEqual(PartSlicer.partCount(fileSize: 8192, partSize: 4096), 2)
        XCTAssertEqual(PartSlicer.partLength(partNumber: 3, fileSize: 10_000, partSize: 4096), 1808)
        XCTAssertEqual(PartSlicer.partLength(partNumber: 4, fileSize: 10_000, partSize: 4096), 0)
    }

    func testSlicesMatchSourceByteRangesAndReassembleToSameChecksum() async throws {
        let source = try makeRandomFile(in: directory, size: 3 * (1 << 20) + 12_345)
        let original = try Data(contentsOf: source)
        let partSize = 1 << 20
        var reassembled = Data()
        for number in 1...PartSlicer.partCount(fileSize: Int64(original.count), partSize: partSize) {
            let destination = directory.appendingPathComponent("p\(number)")
            let length = try await PartSlicer().slice(source: source, partNumber: number, partSize: partSize, to: destination)
            let slice = try Data(contentsOf: destination)
            let expected = original.subdata(in: (number - 1) * partSize ..< min(original.count, number * partSize))
            XCTAssertEqual(Int(length), slice.count)
            XCTAssertEqual(sha256(slice), sha256(expected), "part \(number)")
            reassembled.append(slice)
        }
        XCTAssertEqual(sha256(reassembled), sha256(original))
    }

    func testReslicingOverwritesStalePartFile() async throws {
        let source = try makeRandomFile(in: directory, size: 5000)
        let destination = directory.appendingPathComponent("p")
        try Data(repeating: 0xFF, count: 9000).write(to: destination)
        _ = try await PartSlicer().slice(source: source, partNumber: 2, partSize: 4096, to: destination)
        XCTAssertEqual(try Data(contentsOf: destination).count, 904)
    }

    func testPartBeyondEndOfFileThrows() async throws {
        let source = try makeRandomFile(in: directory, size: 100)
        do {
            _ = try await PartSlicer().slice(source: source, partNumber: 2, partSize: 100, to: directory.appendingPathComponent("p"))
            XCTFail("expected failure")
        } catch {
            XCTAssertEqual(error as? PartSlicerError, .partOutOfRange)
        }
    }
}
