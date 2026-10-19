import CoreGraphics
import simd

/// One object the detector keeps seeing in the same place, in world coordinates.
nonisolated struct DetectionTrack: Sendable, Equatable {
    let category: String
    let label: String
    let center: SIMD3<Float>
    /// Horizontal extent, vertical extent, depth extent, in metres.
    let size: SIMD3<Float>
    let hits: Int
    let confidenceSum: Float

    var meanConfidence: Float { confidenceSum / Float(max(hits, 1)) }

    /// Running mean of position and size, so a box that jitters between frames settles.
    func merging(center newCenter: SIMD3<Float>, size newSize: SIMD3<Float>, confidence: Float) -> DetectionTrack {
        let count = Float(hits)
        return DetectionTrack(
            category: category,
            label: label,
            center: (center * count + newCenter) / (count + 1),
            size: (size * count + newSize) / (count + 1),
            hits: hits + 1,
            confidenceSum: confidenceSum + confidence
        )
    }

    var asDetection: Detection {
        Detection(label: label, category: category, confidence: meanConfidence, boundingBox: .zero, worldCenter: center, worldSize: size)
    }
}

/// Fuses world-lifted detections of one room over time: the same category seen again near a
/// track joins it, and only tracks seen often enough with enough confidence count.
nonisolated struct DetectionAccumulator: Sendable, Equatable {
    struct Configuration: Sendable, Equatable {
        var mergeRadius: Float = 0.4
        /// Large objects jitter more; a track's merge radius grows to half its footprint, up to this.
        var maximumMergeRadius: Float = 1.0
        var minimumHits = 3
        var minimumMeanConfidence: Float = 0.5
        var maximumTracks = 48
        var acceptedCategories = ClassMapper.engineCategories
    }

    let configuration: Configuration
    let tracks: [DetectionTrack]

    init(configuration: Configuration = Configuration(), tracks: [DetectionTrack] = []) {
        self.configuration = configuration
        self.tracks = tracks
    }

    var confirmed: [DetectionTrack] {
        tracks.filter(isConfirmed)
    }

    func isConfirmed(_ track: DetectionTrack) -> Bool {
        track.hits >= configuration.minimumHits && track.meanConfidence >= configuration.minimumMeanConfidence
    }

    /// Each track takes at most one detection per batch, so one frame's duplicate boxes cannot confirm it alone.
    func adding(_ detections: [Detection]) -> DetectionAccumulator {
        var updated = tracks
        var matchedThisBatch = Set<Int>()
        for detection in detections where configuration.acceptedCategories.contains(detection.category) {
            guard let center = detection.worldCenter, let size = detection.worldSize else { continue }
            if let index = nearestTrack(in: updated, category: detection.category, center: center, excluding: matchedThisBatch) {
                updated[index] = updated[index].merging(center: center, size: size, confidence: detection.confidence)
                matchedThisBatch.insert(index)
                continue
            }
            let track = DetectionTrack(
                category: detection.category, label: detection.label, center: center, size: size,
                hits: 1, confidenceSum: detection.confidence
            )
            guard let withRoom = makingRoom(in: updated, protecting: matchedThisBatch) else { continue }
            updated = withRoom.tracks + [track]
            matchedThisBatch = withRoom.protected.union([updated.count - 1])
        }
        return DetectionAccumulator(configuration: configuration, tracks: updated)
    }

    func mergeRadius(of track: DetectionTrack) -> Float {
        let footprint = max(track.size.x, track.size.z)
        return min(configuration.maximumMergeRadius, max(configuration.mergeRadius, footprint / 2))
    }

    private func nearestTrack(
        in tracks: [DetectionTrack], category: String, center: SIMD3<Float>, excluding: Set<Int>
    ) -> Int? {
        tracks.indices
            .filter { !excluding.contains($0) && tracks[$0].category == category }
            .map { (index: $0, distance: simd_distance(tracks[$0].center, center)) }
            .filter { $0.distance <= mergeRadius(of: tracks[$0.index]) }
            .min { $0.distance < $1.distance }?
            .index
    }

    /// At the cap, the oldest of the least-seen unconfirmed tracks gives way; confirmed tracks never do.
    private func makingRoom(
        in tracks: [DetectionTrack], protecting protected: Set<Int>
    ) -> (tracks: [DetectionTrack], protected: Set<Int>)? {
        guard tracks.count >= configuration.maximumTracks else { return (tracks, protected) }
        let evictable = tracks.indices.filter { !protected.contains($0) && !isConfirmed(tracks[$0]) }
        guard let victim = evictable.min(by: { tracks[$0].hits < tracks[$1].hits }) else { return nil }
        let remaining = tracks.enumerated().filter { $0.offset != victim }.map(\.element)
        let shifted = Set(protected.map { $0 > victim ? $0 - 1 : $0 })
        return (remaining, shifted)
    }
}
