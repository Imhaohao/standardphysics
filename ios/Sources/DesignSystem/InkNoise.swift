import CoreGraphics

/// SplitMix64, so grain and brush texture are identical on every render.
nonisolated struct SeededRandom {
    private var state: UInt64

    init(seed: UInt64) {
        state = seed
    }

    mutating func next() -> UInt64 {
        state &+= 0x9E37_79B9_7F4A_7C15
        var mixed = state
        mixed = (mixed ^ (mixed >> 30)) &* 0xBF58_476D_1CE4_E5B9
        mixed = (mixed ^ (mixed >> 27)) &* 0x94D0_49BB_1331_11EB
        return mixed ^ (mixed >> 31)
    }

    mutating func unit() -> CGFloat {
        CGFloat(next() >> 11) / CGFloat(1 << 53)
    }
}

/// One-dimensional value noise in 0...1, smooth between integer knots.
nonisolated enum InkNoise {
    static func value(_ x: CGFloat, seed: UInt64) -> CGFloat {
        let knot = floor(x)
        let fraction = x - knot
        let eased = fraction * fraction * (3 - 2 * fraction)
        let left = hash(Int64(knot), seed: seed)
        let right = hash(Int64(knot) + 1, seed: seed)
        return left + (right - left) * eased
    }

    private static func hash(_ index: Int64, seed: UInt64) -> CGFloat {
        var random = SeededRandom(seed: seed &+ UInt64(bitPattern: index) &* 0x2545_F491_4F6C_DD1D)
        return random.unit()
    }
}
