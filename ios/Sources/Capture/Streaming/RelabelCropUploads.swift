import Foundation
import os

/// Uploads a room's relabel crops that have no artifact yet, a few at a time, and records the
/// artifact ids in `rooms/<n>.relabel.json` so a resend after a relaunch does not upload again.
nonisolated enum RelabelCropUploads {
    static let parallelUploads = 4

    private static let logger = Logger(subsystem: "com.tarunyadgirkar.standardphysics", category: "streaming")

    /// Returns how many crops were uploaded. Stops starting new uploads once `budget` has passed,
    /// so finishing the scan never waits long on a slow link; the rest go on the next resend.
    @concurrent
    static func uploadPending(
        forRoomAt roomURL: URL, scanID: String, uploader: any CropUploading, budget: Duration
    ) async -> Int {
        guard var file = RelabelCropFile.load(forRoomAt: roomURL), !file.pendingUploads.isEmpty else { return 0 }
        let deadline = ContinuousClock.now + budget
        var artifactIDs: [String: String] = [:]
        for batch in batches(of: file.pendingUploads, size: parallelUploads) {
            guard ContinuousClock.now < deadline else { break }
            let uploaded = await upload(batch, forRoomAt: roomURL, scanID: scanID, uploader: uploader)
            artifactIDs.merge(uploaded) { _, newer in newer }
        }
        guard !artifactIDs.isEmpty else { return 0 }
        file.record(artifactIDs: artifactIDs)
        do {
            try file.encoded().write(to: RelabelCropFile.url(forRoomAt: roomURL), options: [.atomic])
        } catch {
            logger.error("Relabel crop ids were not saved: \(error.localizedDescription)")
        }
        return artifactIDs.count
    }

    static func batches<Element>(of items: [Element], size: Int) -> [[Element]] {
        stride(from: 0, to: items.count, by: max(size, 1)).map { start in
            Array(items[start..<min(start + max(size, 1), items.count)])
        }
    }

    /// Object id to artifact id, for the crops that uploaded.
    private static func upload(
        _ entries: [RelabelCropFile.Entry], forRoomAt roomURL: URL, scanID: String, uploader: any CropUploading
    ) async -> [String: String] {
        await withTaskGroup(of: (String, String)?.self) { group in
            for entry in entries {
                let cropURL = RelabelCropFile.cropURL(of: entry, forRoomAt: roomURL)
                group.addTask {
                    guard let jpeg = try? Data(contentsOf: cropURL),
                          let artifactID = try? await uploader.uploadCrop(jpeg: jpeg, scanID: scanID)
                    else { return nil }
                    return (entry.objectID, artifactID)
                }
            }
            var uploaded: [String: String] = [:]
            for await result in group {
                if case let (objectID, artifactID)? = result { uploaded[objectID] = artifactID }
            }
            return uploaded
        }
    }
}
