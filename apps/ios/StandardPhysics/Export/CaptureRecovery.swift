import Foundation
import RoomPlan

enum CaptureRecovery {
    /// How long a walk's folder may sit unfinished before it counts as abandoned. A walk
    /// still saving its room writes to its folder well inside this.
    static let abandonedAfter: TimeInterval = 10 * 60

    /// Deletes the folders of walks that were cancelled or never finished saving.
    ///
    /// A walk writes room.recovery.json as it ends and capture.json once its room is
    /// saved, so a folder with the first and not the second, untouched for
    /// `abandonedAfter`, is a walk nobody finished. Home used to offer each one back
    /// as "Recover saved room", and every cancelled walk added another button.
    static func discardAbandoned(in root: URL, now: Date = Date()) {
        for directory in abandoned(in: root, now: now) {
            try? FileManager.default.removeItem(at: directory)
        }
    }

    static func abandoned(in root: URL, now: Date = Date()) -> [URL] {
        let directories = (try? FileManager.default.contentsOfDirectory(at: root,
            includingPropertiesForKeys: [.contentModificationDateKey], options: .skipsHiddenFiles)) ?? []
        return directories.filter { directory in
            let marker = directory.appendingPathComponent("room.recovery.json")
            guard FileManager.default.fileExists(atPath: marker.path),
                  !FileManager.default.fileExists(atPath: directory.appendingPathComponent("capture.json").path)
            else { return false }
            return now.timeIntervalSince(lastTouched(directory)) > abandonedAfter
        }
    }

    private static func lastTouched(_ directory: URL) -> Date {
        let files = (try? FileManager.default.contentsOfDirectory(at: directory,
            includingPropertiesForKeys: [.contentModificationDateKey])) ?? []
        return ([directory] + files).compactMap {
            try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate
        }.max() ?? .distantPast
    }

    static func recover(from directory: URL) throws -> CapturedScan {
        let room = try JSONDecoder().decode(CapturedRoom.self,
            from: Data(contentsOf: directory.appendingPathComponent("room.recovery.json")))
        let posesURL = directory.appendingPathComponent("poses.json")
        if !FileManager.default.fileExists(atPath: posesURL.path) {
            try Data("[]".utf8).write(to: posesURL, options: .atomic)
        }
        guard let recording = RecordingResult.recovered(from: directory) else { throw RecoveryError.invalidPoses }
        var engine = CoverageEngine()
        let coverage = engine.reconcile(finalSurfaces: RoomCoverage.snapshots(from: room))
        return try ScanExporter.export(room: room, recording: recording, coverage: coverage, directory: directory)
    }

    enum RecoveryError: Error { case invalidPoses }
}
