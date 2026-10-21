import Foundation

/// Finished reports kept on the phone, so they are still there after a relaunch.
nonisolated protocol ReportStoring: Sendable {
    func loadAll() async -> [ScanReport]
    func save(_ report: ScanReport) async throws
    func delete(scanID: UUID) async throws
}

/// `Application Support/Reports/<uuid>.json`, one file per report, each written atomically so a
/// kill mid-save leaves the previous version readable.
actor FileReportStore: ReportStoring {
    nonisolated static var defaultRoot: URL {
        URL.applicationSupportDirectory.appending(path: "Reports", directoryHint: .isDirectory)
    }

    nonisolated let root: URL
    private let writer: any AtomicFileWriting

    init(root: URL = FileReportStore.defaultRoot, writer: any AtomicFileWriting = AtomicFileWriter()) {
        self.root = root
        self.writer = writer
    }

    nonisolated func fileURL(for scanID: UUID) -> URL {
        root.appending(path: "\(scanID.uuidString).json")
    }

    func loadAll() -> [ScanReport] {
        let entries = (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? []
        let decoder = JSONDecoder()
        return entries
            .filter { $0.pathExtension == "json" && !AtomicFileWriter.isTemporaryFile($0) }
            .compactMap { try? decoder.decode(ScanReport.self, from: Data(contentsOf: $0)) }
            .sorted { $0.completedAt > $1.completedAt }
    }

    func save(_ report: ScanReport) throws {
        try ProtectedDirectory.create(root)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        try writer.write(try encoder.encode(report), to: fileURL(for: report.scanID))
    }

    func delete(scanID: UUID) throws {
        let url = fileURL(for: scanID)
        guard FileManager.default.fileExists(atPath: url.path) else { return }
        try FileManager.default.removeItem(at: url)
    }
}
