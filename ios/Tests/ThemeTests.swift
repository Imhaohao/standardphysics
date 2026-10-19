import XCTest
import UIKit
@testable import StandardPhysics

final class ThemeTests: XCTestCase {
    @MainActor
    func testBundledFontsAreRegistered() {
        let families = Set(UIFont.familyNames)
        for family in [Theme.Typography.displayFamily, Theme.Typography.bodyFamily, Theme.Typography.figureFamily] {
            XCTAssertTrue(families.contains(family), "\(family) is not registered")
        }
    }
}
