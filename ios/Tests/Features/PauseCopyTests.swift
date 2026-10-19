import XCTest
@testable import StandardPhysics

final class PauseCopyTests: XCTestCase {
    private let reasons: [PauseReason] = [.appInactive, .backgrounded, .sessionInterrupted, .trackingLost, .thermal, .user]

    func testAPauseYouChoseReadsPlainly() {
        let copy = PauseCopy(.user)
        XCTAssertEqual("\(copy.title). \(copy.message)", "Scan paused. Tap Continue when you're ready.")
    }

    func testEveryReasonExplainsItselfDifferently() {
        let messages = Set(reasons.map { PauseCopy($0).message })
        XCTAssertEqual(messages.count, reasons.count)
    }

    func testEveryReasonTellsYouHowToCarryOn() {
        for reason in reasons {
            XCTAssertTrue(PauseCopy(reason).message.contains("tap Continue") || PauseCopy(reason).message.contains("Tap Continue"), "\(reason)")
        }
    }

    func testSpecificReasons() {
        XCTAssertEqual(PauseCopy(.thermal).title, "Your iPhone needs to cool down")
        XCTAssertEqual(PauseCopy(.thermal).systemImage, "thermometer.high")
        XCTAssertEqual(PauseCopy(.trackingLost).title, "The camera lost its place")
        XCTAssertTrue(PauseCopy(.appInactive).message.contains("Control Center"))
        XCTAssertTrue(PauseCopy(.backgrounded).message.contains("saved everything"))
        XCTAssertTrue(PauseCopy(.sessionInterrupted).message.contains("camera"))
    }

    func testCopyAvoidsEmDashesAndShouting() {
        for reason in reasons {
            let copy = PauseCopy(reason)
            for text in [copy.title, copy.message] {
                XCTAssertFalse(text.contains("\u{2014}"), text)
                XCTAssertFalse(text.contains("!"), text)
            }
        }
    }
}
