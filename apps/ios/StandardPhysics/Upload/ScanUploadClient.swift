import CryptoKit
import Foundation

enum ScanState: String, Codable, Equatable, Sendable {
    case uploading
    case measuring
    case checking
    case ready
    case failed

    var displayText: String {
        switch self {
        case .uploading: "Uploading"
        case .measuring: "Measuring your shop"
        case .checking: "Checking"
        case .ready: "Ready"
        case .failed: "Try the upload again"
        }
    }
}

struct RemoteScan: Decodable {
    let id: String
    let state: ScanState
}

struct ScanUploadClient {
    private struct CreateScanRequest: Encodable {
        let name: String
        let deviceModel: String
        let durationSeconds: TimeInterval

        enum CodingKeys: String, CodingKey {
            case name
            case deviceModel = "device_model"
            case durationSeconds = "duration_seconds"
        }
    }

    let baseURL: URL
    var session: URLSession = .shared

    func createScan(name: String, duration: TimeInterval) async throws -> RemoteScan {
        var request = URLRequest(url: baseURL.appendingPathComponent("api/scans"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(CreateScanRequest(
            name: name,
            deviceModel: DeviceModel.current,
            durationSeconds: duration
        ))
        return try await send(request, expectedStatus: 201)
    }

    func upload(_ artifact: CaptureArtifact, to scanID: String) async throws {
        let url = baseURL
            .appendingPathComponent("api/scans")
            .appendingPathComponent(scanID)
            .appendingPathComponent("artifacts")
            .appendingPathComponent(artifact.id)
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue(try SHA256Digest.hexDigest(of: artifact.fileURL), forHTTPHeaderField: "X-Checksum-SHA256")
        request.setValue(artifact.kind.rawValue, forHTTPHeaderField: "X-Artifact-Kind")
        let (_, response) = try await session.upload(for: request, fromFile: artifact.fileURL)
        try validate(response, expectedStatus: 200...201)
    }

    func complete(scanID: String) async throws -> RemoteScan {
        var request = URLRequest(
            url: baseURL.appendingPathComponent("api/scans")
                .appendingPathComponent(scanID)
                .appendingPathComponent("complete")
        )
        request.httpMethod = "POST"
        return try await send(request, expectedStatus: 200)
    }

    func scan(id: String) async throws -> RemoteScan {
        let request = URLRequest(
            url: baseURL.appendingPathComponent("api/scans").appendingPathComponent(id)
        )
        return try await send(request, expectedStatus: 200)
    }

    private func send(_ request: URLRequest, expectedStatus: Int) async throws -> RemoteScan {
        let (data, response) = try await session.data(for: request)
        try validate(response, expectedStatus: expectedStatus...expectedStatus)
        return try JSONDecoder().decode(RemoteScan.self, from: data)
    }

    private func validate(_ response: URLResponse, expectedStatus: ClosedRange<Int>) throws {
        guard let response = response as? HTTPURLResponse,
              expectedStatus.contains(response.statusCode) else {
            throw UploadClientError.unexpectedResponse
        }
    }
}

enum SHA256Digest {
    static func hexDigest(of fileURL: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: fileURL)
        defer { try? handle.close() }
        var hasher = SHA256()
        while let data = try handle.read(upToCount: 1_048_576), !data.isEmpty {
            hasher.update(data: data)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}

enum UploadClientError: Error {
    case unexpectedResponse
}

private enum DeviceModel {
    static var current: String {
        var systemInfo = utsname()
        uname(&systemInfo)
        let mirror = Mirror(reflecting: systemInfo.machine)
        return mirror.children.reduce(into: "") { result, element in
            guard let value = element.value as? Int8, value != 0 else { return }
            result.append(Character(UnicodeScalar(UInt8(value))))
        }
    }
}
