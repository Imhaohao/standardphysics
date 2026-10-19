import CoreGraphics

nonisolated struct LabelPlacementRequest: Sendable, Equatable {
    let id: String
    let anchor: CGPoint
    let size: CGSize
    let priority: Int
}

nonisolated struct LabelPlacement: Sendable, Equatable {
    let id: String
    let anchor: CGPoint
    let frame: CGRect
}

/// Greedy screen-space placement: the most important labels claim space first, each trying a few
/// spots around its anchor; a label with nowhere free is hidden for this frame.
nonisolated enum LabelLayout {
    static let anchorGap: CGFloat = 10
    static let labelSpacing: CGFloat = 4

    static func place(_ requests: [LabelPlacementRequest], in bounds: CGRect) -> [LabelPlacement] {
        let ordered = requests.sorted { ($0.priority, $1.id) > ($1.priority, $0.id) }
        return ordered.reduce(into: [LabelPlacement]()) { placed, request in
            let occupied = placed.map { $0.frame.insetBy(dx: -labelSpacing, dy: -labelSpacing) }
            let free = candidateFrames(for: request).first { frame in
                bounds.contains(frame) && !occupied.contains { $0.intersects(frame) }
            }
            if let free {
                placed.append(LabelPlacement(id: request.id, anchor: request.anchor, frame: free))
            }
        }
    }

    /// Above, below, right, left, then further above, in that order of preference.
    static func candidateFrames(for request: LabelPlacementRequest) -> [CGRect] {
        let size = request.size
        let horizontalReach = size.width / 2 + anchorGap
        let verticalReach = size.height / 2 + anchorGap
        let offsets = [
            CGVector(dx: 0, dy: -verticalReach),
            CGVector(dx: 0, dy: verticalReach),
            CGVector(dx: horizontalReach, dy: 0),
            CGVector(dx: -horizontalReach, dy: 0),
            CGVector(dx: 0, dy: -verticalReach * 2 - labelSpacing),
            CGVector(dx: horizontalReach, dy: -verticalReach),
            CGVector(dx: -horizontalReach, dy: -verticalReach),
        ]
        return offsets.map { offset in
            CGRect(
                x: request.anchor.x + offset.dx - size.width / 2,
                y: request.anchor.y + offset.dy - size.height / 2,
                width: size.width,
                height: size.height
            )
        }
    }
}
