import Foundation
import RoomPlan

enum CaptureRecovery {
    static func directories(in root: URL) -> [URL] {
        let directories = (try? FileManager.default.contentsOfDirectory(at: root,
            includingPropertiesForKeys: [.isDirectoryKey], options: .skipsHiddenFiles)) ?? []
        return directories.filter {
            FileManager.default.fileExists(atPath: $0.appendingPathComponent("room.recovery.json").path)
                && !FileManager.default.fileExists(atPath: $0.appendingPathComponent("capture.json").path)
        }
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
