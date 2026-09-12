import XCTest
@testable import StandardPhysics

final class ServiceAddressTests: XCTestCase {
    func testAcceptsHostedHTTPSAndLocalDevelopmentHost() throws {
        XCTAssertEqual(try ServiceAddress.parse(" https://example.com/workspace ").host, "example.com")
        XCTAssertEqual(try ServiceAddress.parse("http://studio.local:8787").port, 8787)
        XCTAssertEqual(try ServiceAddress.parse("http://192.168.1.2:8787").host, "192.168.1.2")
    }

    func testRejectsUntrustedAddressShapes() {
        for value in ["file:///etc/passwd", "javascript:alert(1)", "/relative", "https://", "http://example.com",
                      "https://user:secret@example.com", "https://example.com?token=secret", "https://example.com/#token"] {
            XCTAssertThrowsError(try ServiceAddress.parse(value), value)
        }
    }
}
