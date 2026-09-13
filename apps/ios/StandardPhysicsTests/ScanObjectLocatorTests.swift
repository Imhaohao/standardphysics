import XCTest
import simd
@testable import StandardPhysics

final class ScanObjectLocatorTests: XCTestCase {
    func testMatchesRotatedMeasuredObjectWithoutMovingItsGeometry() {
        var transform = simd_float4x4(simd_quatf(angle: .pi / 2, axis: SIMD3(0, 1, 0)))
        transform.columns.3 = SIMD4(2, 0, 0, 1)
        let table = SurfaceSnapshot(id: UUID(), width: 2, height: 1, transform: transform,
            confidence: .high, isWall: false, shape: .box(size: SIMD3(2, 1, 0.4)), kind: "table")
        let locator = ScanObjectLocator(objects: [table])
        XCTAssertEqual(locator.object(at: SIMD3(2, 0, 0.8))?.id, table.id)
        XCTAssertNil(locator.object(at: SIMD3(2.8, 0, 0)))
        XCTAssertNil(ScanObjectLocator(objects: [table, table]).object(at: SIMD3(2, 0, 0)))
    }
}
