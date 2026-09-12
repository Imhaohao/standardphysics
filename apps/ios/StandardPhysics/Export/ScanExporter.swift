import Foundation
import RoomPlan

enum ArtifactKind: String, Codable, Sendable {
    case roomUSDZ = "room_usdz"
    case roomJSON = "room_json"
    case roomMetadata = "room_metadata"
    case walkthroughMP4 = "walkthrough_mp4"
    case frames
    case poses
    case coverage
}

struct CaptureArtifact: Identifiable, Codable, Sendable {
    let id: String
    let kind: ArtifactKind
    let fileURL: URL
}

struct CapturedScan: Identifiable, Codable {
    let id: UUID
    let directory: URL
    let roomURL: URL
    let duration: TimeInterval
    let artifacts: [CaptureArtifact]
    let name: String?
    var captureNotice: String? = nil

    func renamed(_ name: String) throws -> CapturedScan {
        let updated = CapturedScan(
            id: id,
            directory: directory,
            roomURL: roomURL,
            duration: duration,
            artifacts: artifacts,
            name: name,
            captureNotice: captureNotice
        )
        try JSONEncoder.standardPhysics.encode(updated).write(
            to: directory.appendingPathComponent("capture.json"),
            options: .atomic
        )
        return updated
    }
}

enum ScanExporter {
    private struct CoverageValue: Codable {
        let observedFraction: Double
        let viewpointCount: Int

        enum CodingKeys: String, CodingKey {
            case observedFraction = "observed_fraction"
            case viewpointCount = "viewpoint_count"
        }
    }

    static func makeCaptureDirectory(id: UUID = UUID()) throws -> URL {
        let root = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        ).appendingPathComponent("Captures", isDirectory: true)
        let directory = root.appendingPathComponent(id.uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory
    }

    static func export(
        room: CapturedRoom,
        recording: RecordingResult,
        coverage: CoverageSnapshot,
        directory: URL
    ) throws -> CapturedScan {
        let roomURL = directory.appendingPathComponent("room.usdz")
        let roomJSONURL = directory.appendingPathComponent("room.json")
        let metadataURL = directory.appendingPathComponent("room.metadata.json")
        let coverageURL = directory.appendingPathComponent("coverage.json")

        try room.export(
            to: roomURL,
            metadataURL: metadataURL,
            exportOptions: [.parametric, .mesh]
        )
        try JSONEncoder.standardPhysics.encode(room).write(to: roomJSONURL, options: .atomic)
        let coverageByID = Dictionary(uniqueKeysWithValues: coverage.surfaces.map {
            ($0.id.uuidString, CoverageValue(
                observedFraction: $0.observedFraction,
                viewpointCount: $0.viewpointCount
            ))
        })
        try JSONEncoder.standardPhysics.encode(coverageByID).write(to: coverageURL, options: .atomic)

        var artifacts = [
            CaptureArtifact(id: "room-usdz", kind: .roomUSDZ, fileURL: roomURL),
            CaptureArtifact(id: "room-json", kind: .roomJSON, fileURL: roomJSONURL),
            CaptureArtifact(id: "room-metadata", kind: .roomMetadata, fileURL: metadataURL),
            CaptureArtifact(id: "poses", kind: .poses, fileURL: recording.posesURL),
            CaptureArtifact(id: "coverage", kind: .coverage, fileURL: coverageURL)
        ]
        if let videoURL = recording.videoURL {
            artifacts.append(CaptureArtifact(id: "walkthrough", kind: .walkthroughMP4, fileURL: videoURL))
        }
        artifacts.append(contentsOf: recording.frameURLs.enumerated().map { index, fileURL in
            CaptureArtifact(
                id: String(format: "frame-%04d", index),
                kind: .frames,
                fileURL: fileURL
            )
        })

        let scan = CapturedScan(
            id: room.identifier,
            directory: directory,
            roomURL: roomURL,
            duration: recording.duration,
            artifacts: artifacts,
            name: nil,
            captureNotice: recording.videoURL == nil ? "Your room is saved. Scan again to add a walkthrough." : nil
        )
        try JSONEncoder.standardPhysics.encode(scan).write(
            to: directory.appendingPathComponent("capture.json"),
            options: .atomic
        )
        return scan
    }
}

enum CaptureLibrary {
    static func all() -> [CapturedScan] {
        guard let root = try? FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        ).appendingPathComponent("Captures", isDirectory: true),
        let directories = try? FileManager.default.contentsOfDirectory(
            at: root,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: .skipsHiddenFiles
        ) else { return [] }

        return directories.compactMap { directory in
            let manifest = directory.appendingPathComponent("capture.json")
            return try? JSONDecoder().decode(CapturedScan.self, from: Data(contentsOf: manifest))
        }.sorted { left, right in
            let leftDate = (try? left.directory.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .distantPast
            let rightDate = (try? right.directory.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .distantPast
            return leftDate > rightDate
        }
    }
}
