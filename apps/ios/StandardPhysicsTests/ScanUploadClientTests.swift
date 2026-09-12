import XCTest
@testable import StandardPhysics

final class ScanUploadClientTests: XCTestCase {
    override func tearDown() {
        URLProtocolStub.handler = nil
        super.tearDown()
    }

    func testUploadsContractHeadersAndFinalizesTheScan() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let artifactURL = directory.appendingPathComponent("room.json")
        try Data("abc".utf8).write(to: artifactURL)

        var uploadedRequest: URLRequest?
        URLProtocolStub.handler = { request in
            switch (request.httpMethod, request.url?.path) {
            case ("POST", "/api/scans"):
                return (201, #"{"id":"scan-123","state":"uploading"}"#.data(using: .utf8)!)
            case ("PUT", "/api/scans/scan-123/artifacts/room-json"):
                uploadedRequest = request
                return (201, Data("{}".utf8))
            case ("POST", "/api/scans/scan-123/complete"):
                return (200, #"{"id":"scan-123","state":"measuring"}"#.data(using: .utf8)!)
            default:
                XCTFail("Unexpected request: \(request)")
                return (500, Data())
            }
        }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        let client = ScanUploadClient(
            baseURL: URL(string: "https://standard.physics")!,
            session: URLSession(configuration: configuration)
        )
        let remote = try await client.createScan(name: "Tea House", duration: 30)
        try await client.upload(
            CaptureArtifact(id: "room-json", kind: "room_json", fileURL: artifactURL),
            to: remote.id
        )
        let completed = try await client.complete(scanID: remote.id)

        XCTAssertEqual(uploadedRequest?.value(forHTTPHeaderField: "X-Artifact-Kind"), "room_json")
        XCTAssertEqual(
            uploadedRequest?.value(forHTTPHeaderField: "X-Checksum-SHA256"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )
        XCTAssertEqual(completed.state, .measuring)
    }
}

private final class URLProtocolStub: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        do {
            let (status, data) = try Self.handler?(request) ?? (500, Data())
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: status,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
