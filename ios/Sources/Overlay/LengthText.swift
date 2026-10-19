import Foundation

/// Inches lead because ADA and CBC thresholds are written in inches; centimetres follow.
nonisolated struct LengthText: Sendable, Equatable {
    static let metersPerInch: Float = 0.0254

    let inches: String
    let centimeters: String

    init(meters: Float) {
        let meters = max(0, meters)
        let halfInches = (meters / Self.metersPerInch * 2).rounded()
        let wholeInches = Int(halfInches) / 2
        let hasHalf = !Int(halfInches).isMultiple(of: 2)
        inches = hasHalf ? "\(wholeInches)½ in" : "\(wholeInches) in"
        centimeters = "\(Int((meters * 100).rounded())) cm"
    }
}
