import XCTest
@testable import StandardPhysics

final class PresignValidationTests: XCTestCase {
    private let host = "acct.r2.cloudflarestorage.com"
    private let policy = StorageHostPolicy(allowedHosts: [".r2.cloudflarestorage.com"], allowsLocalHTTP: false)

    private func part(_ number: Int, url: String? = nil, headers: [String: String] = [:]) -> PresignedPart {
        PresignedPart(partNumber: number, url: URL(string: url ?? "https://\(host)/bucket/key?X-Amz-Signature=x&partNumber=\(number)")!, headers: headers)
    }

    private func response(_ parts: [PresignedPart], expires: Int = 900, host: String? = nil) -> PresignResponse {
        PresignResponse(parts: parts, expiresInSecs: expires, host: host ?? self.host)
    }

    func testAcceptsRequestedPartsOnTheNamedHost() throws {
        let validated = try PresignValidation.validate(response([part(1), part(2)]), requested: [1, 2], policy: policy)
        XCTAssertEqual(validated.parts.map(\.partNumber), [1, 2])
        XCTAssertEqual(validated.expiresInSecs, 900)
    }

    func testRejectsPartsThatWereNotRequested() {
        XCTAssertThrowsError(try PresignValidation.validate(response([part(1), part(3)]), requested: [1], policy: policy))
        XCTAssertThrowsError(try PresignValidation.validate(response([part(1), part(1)]), requested: [1], policy: policy))
    }

    func testRejectsPlainHTTPAndOtherHosts() {
        let insecure = part(1, url: "http://\(host)/bucket/key")
        XCTAssertThrowsError(try PresignValidation.validate(response([insecure]), requested: [1], policy: policy))
        let elsewhere = part(1, url: "https://other.r2.cloudflarestorage.com/bucket/key")
        XCTAssertThrowsError(try PresignValidation.validate(response([elsewhere]), requested: [1], policy: policy), "must match the host the server named")
        let notAllowed = part(1, url: "https://evil.example.com/bucket/key")
        XCTAssertThrowsError(try PresignValidation.validate(response([notAllowed], host: "evil.example.com"), requested: [1], policy: policy))
    }

    func testWithoutANamedHostTheAllowlistStillApplies() throws {
        XCTAssertNoThrow(try PresignValidation.validate(PresignResponse(parts: [part(1)], expiresInSecs: 900), requested: [1], policy: policy))
        let other = PresignResponse(parts: [part(1, url: "https://evil.example.com/k")], expiresInSecs: 900)
        XCTAssertThrowsError(try PresignValidation.validate(other, requested: [1], policy: policy))
    }

    func testOnlyStorageHeadersAreKept() throws {
        let headers = ["Content-Type": "application/json", "x-amz-checksum-sha256": "abc", "Authorization": "Bearer stolen", "Host": "x"]
        let validated = try PresignValidation.validate(response([part(1, headers: headers)]), requested: [1], policy: policy)
        XCTAssertEqual(validated.parts[0].headers, ["Content-Type": "application/json", "x-amz-checksum-sha256": "abc"])
    }

    func testExpiryIsClampedToSaneBounds() throws {
        XCTAssertEqual(try PresignValidation.validate(response([part(1)], expires: 5), requested: [1], policy: policy).expiresInSecs, 60)
        XCTAssertEqual(try PresignValidation.validate(response([part(1)], expires: 999_999), requested: [1], policy: policy).expiresInSecs, 3600)
    }

    func testPresignResponseDecodesTheHost() throws {
        let json = #"{"expires_in_secs":900,"host":"acct.r2.cloudflarestorage.com","parts":[]}"#
        let decoded = try WireCoding.decoder().decode(PresignResponse.self, from: Data(json.utf8))
        XCTAssertEqual(decoded.host, "acct.r2.cloudflarestorage.com")
    }

    func testPolicyReadsSpaceSeparatedHostsAndMatchesSubdomains() {
        let policy = StorageHostPolicy(allowedHosts: ["localhost", ".r2.cloudflarestorage.com"])
        XCTAssertTrue(policy.allows(host: "localhost"))
        XCTAssertTrue(policy.allows(host: "ACCT.r2.cloudflarestorage.com"))
        XCTAssertFalse(policy.allows(host: "r2.cloudflarestorage.com.evil.com"))
        XCTAssertFalse(policy.allows(host: "notlocalhost"))
    }
}
