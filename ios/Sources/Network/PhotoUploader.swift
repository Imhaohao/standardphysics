import CryptoKit
import Foundation

/// Sends one photo through the same multipart flow the background uploader uses (create,
/// presign, PUT each part, complete), but in the foreground, because the owner is waiting on
/// the answer and the server needs the artifact id the completion returns.
nonisolated struct PhotoUploader: Sendable {
    static let maximumPartCount = 10_000
    static let contentType = "image/jpeg"

    let api: any UploadAPI
    let storage: any HTTPTransport
    var policy = StorageHostPolicy.fromInfoPlist()
    var partSize = 8 * 1024 * 1024

    /// Returns the stored photo's artifact id. Relabel crops use the same flow with `kind: .crop`.
    func upload(jpeg: Data, scanID: String, kind: UploadKind = .photo) async throws -> String {
        guard !jpeg.isEmpty else { throw UploadError.emptyFile }
        let body = CreateUploadBody(
            kind: kind.rawValue, filename: "\(kind.rawValue)-\(UUID().uuidString).jpg", contentType: Self.contentType,
            sizeBytes: Int64(jpeg.count), partSize: partSize
        )
        let upload = try await api.createUpload(scanID: scanID, body: body, idempotencyKey: UUID().uuidString)
        let count = try Self.expectedPartCount(of: upload, size: jpeg.count)
        let numbers = Array(1...count)
        let presigned = try PresignValidation.validate(
            try await api.presignParts(scanID: scanID, uploadID: upload.id, partNumbers: numbers),
            requested: numbers, policy: policy
        )
        guard presigned.parts.count == count else { throw APIError.malformedResponse }
        for part in presigned.parts {
            try await put(Self.slice(jpeg, part: part.partNumber, partSize: upload.partSize), to: part)
        }
        return try await api.completeUpload(scanID: scanID, uploadID: upload.id, sha256: Self.sha256Hex(jpeg)).id
    }

    static func expectedPartCount(of upload: UploadInfo, size: Int) throws -> Int {
        let expected = PartSlicer.partCount(fileSize: Int64(size), partSize: upload.partSize)
        guard upload.partSize > 0, expected > 0, upload.partCount == expected, expected <= maximumPartCount else {
            throw APIError.malformedResponse
        }
        return expected
    }

    static func slice(_ data: Data, part number: Int, partSize: Int) -> Data {
        let start = (number - 1) * partSize
        let end = min(data.count, start + partSize)
        return data.subdata(in: start..<end)
    }

    static func sha256Hex(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private func put(_ bytes: Data, to part: PresignedPart) async throws {
        var request = URLRequest(url: part.url)
        request.httpMethod = "PUT"
        part.headers.forEach { request.setValue($0.value, forHTTPHeaderField: $0.key) }
        request.httpBody = bytes
        let response = try await storage.send(request)
        guard response.isSuccess else { throw APIError(response: response) }
    }
}
