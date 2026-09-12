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

        let scanID = UUID(uuidString: "9771B8AC-1A27-4058-A1B1-10E2A3494B2B")!
        var uploadedRequest: URLRequest?
        URLProtocolStub.handler = { request in
            switch (request.httpMethod, request.url?.path) {
            case ("POST", "/api/scans"):
                return (201, #"{"id":"\#(scanID.uuidString)","state":"uploading"}"#.data(using: .utf8)!)
            case ("PUT", "/api/scans/\(scanID.uuidString)/artifacts/room-json"):
                uploadedRequest = request
                return (201, Data("{}".utf8))
            case ("POST", "/api/scans/\(scanID.uuidString)/complete"):
                return (200, #"{"id":"\#(scanID.uuidString)","state":"measuring"}"#.data(using: .utf8)!)
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
            CaptureArtifact(id: "room-json", kind: .roomJSON, fileURL: artifactURL),
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

    func testRejectsMalformedRemoteIdentifier() async throws {
        URLProtocolStub.handler = { _ in
            (201, #"{"id":"not-a-uuid","state":"uploading"}"#.data(using: .utf8)!)
        }

        let client = makeClient()
        do {
            _ = try await client.createScan(name: "Tea House", duration: 30)
            XCTFail("Expected malformed response identifier to fail decoding")
        } catch is DecodingError {
            // The UUID decoder rejects malformed JSON values at the client boundary.
        }
    }

    func testRejectsResponseForADifferentScan() async throws {
        let requestedID = UUID(uuidString: "9771B8AC-1A27-4058-A1B1-10E2A3494B2B")!
        let returnedID = UUID(uuidString: "16C2D1E9-C757-42F9-B55D-7E4DF4F0E8E9")!
        URLProtocolStub.handler = { _ in
            (200, #"{"id":"\#(returnedID.uuidString)","state":"checking"}"#.data(using: .utf8)!)
        }

        do {
            _ = try await makeClient().scan(id: requestedID)
            XCTFail("Expected a mismatched response identifier")
        } catch let error as UploadClientError {
            XCTAssertEqual(error, .mismatchedScanIdentifier)
        }
    }

    private func makeClient() -> ScanUploadClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        return ScanUploadClient(
            baseURL: URL(string: "https://standard.physics")!,
            session: URLSession(configuration: configuration)
        )
    }
}

final class WorkspaceWebViewTests: XCTestCase {
    func testWebOriginRequiresTheSameSchemeHostAndPort() {
        let origin = WebOrigin(url: URL(string: "https://standard.physics:8443/scans")!)

        XCTAssertTrue(origin?.contains(URL(string: "https://standard.physics:8443/scans/123")!) == true)
        XCTAssertFalse(origin?.contains(URL(string: "http://standard.physics:8443/scans/123")!) == true)
        XCTAssertFalse(origin?.contains(URL(string: "https://standard.physics/scans/123")!) == true)
        XCTAssertFalse(origin?.contains(URL(string: "https://other.standard.physics:8443/scans/123")!) == true)
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
