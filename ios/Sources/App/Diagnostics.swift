import Foundation
import Synchronization

/// Debug builds append timing and phase events to `Application Support/diagnostics.jsonl`, so a
/// device run can be read back with `devicectl device copy from`. Release builds record nothing.
nonisolated final class Diagnostics: Sendable {
    static let shared = Diagnostics()
    static let fileName = "diagnostics.jsonl"

    private let queue = DispatchQueue(label: "com.standardphysics.capture.diagnostics", qos: .utility)
    private let url: URL

    init(directory: URL = URL.applicationSupportDirectory) {
        url = directory.appending(path: Self.fileName)
    }

    func record(_ event: String, _ fields: [String: Double] = [:], note: String? = nil) {
        #if DEBUG
        var object: [String: Any] = ["event": event, "t": Date.now.timeIntervalSince1970]
        fields.forEach { object[$0.key] = $0.value }
        if let note { object["note"] = note }
        guard let data = try? JSONSerialization.data(withJSONObject: object) else { return }
        let url = url
        queue.async { Self.append(data + Data("\n".utf8), to: url) }
        #endif
    }

    private static func append(_ line: Data, to url: URL) {
        guard let handle = try? FileHandle(forWritingTo: url) else {
            try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? line.write(to: url)
            return
        }
        defer { try? handle.close() }
        _ = try? handle.seekToEnd()
        try? handle.write(contentsOf: line)
    }
}

/// Counts ticks and records the rate once per window, e.g. rendered overlay frames per second.
nonisolated final class RateMeter: Sendable {
    private struct Window {
        var start: ContinuousClock.Instant?
        var ticks = 0
    }

    private let event: String
    private let window: Duration
    private let state = Mutex(Window())

    init(event: String, window: Duration = .seconds(2)) {
        self.event = event
        self.window = window
    }

    func tick(now: ContinuousClock.Instant = .now) {
        let rate: Double? = state.withLock { window in
            guard let start = window.start else {
                window.start = now
                return nil
            }
            window.ticks += 1
            let elapsed = now - start
            guard elapsed >= self.window else { return nil }
            let seconds = Double(elapsed.components.seconds) + Double(elapsed.components.attoseconds) / 1e18
            let perSecond = Double(window.ticks) / seconds
            window = Window(start: now)
            return perSecond
        }
        if let rate { Diagnostics.shared.record(event, ["per_second": rate]) }
    }
}

/// Wraps a detector to record how long each inference takes and how much it found.
nonisolated struct TimedDetector: ObjectDetecting {
    let base: any ObjectDetecting

    func detect(pixelBuffer: CVPixelBufferWrapper) async throws -> [Detection] {
        let clock = ContinuousClock()
        let start = clock.now
        let detections = try await base.detect(pixelBuffer: pixelBuffer)
        let elapsed = clock.now - start
        Diagnostics.shared.record("detector", [
            "ms": Double(elapsed.components.attoseconds) / 1e15 + Double(elapsed.components.seconds) * 1000,
            "count": Double(detections.count),
        ])
        return detections
    }
}

/// Records how long Finish takes, from tapping it to the report being ready.
final class TimedProcessor: ScanProcessing {
    private let base: any ScanProcessing

    init(base: any ScanProcessing) {
        self.base = base
    }

    func process(_ manifest: ScanManifest, onUpdate: @escaping (ProcessingUpdate) -> Void) async throws -> ScanReport {
        let clock = ContinuousClock()
        let start = clock.now
        let report = try await base.process(manifest, onUpdate: onUpdate)
        let elapsed = clock.now - start
        Diagnostics.shared.record("finish", [
            "ms": Double(elapsed.components.seconds) * 1000 + Double(elapsed.components.attoseconds) / 1e15,
            "rooms": Double(manifest.rooms.count),
            "findings": Double(report.findings.count),
        ])
        return report
    }
}
