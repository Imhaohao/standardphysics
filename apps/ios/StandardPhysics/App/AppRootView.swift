import RoomPlan
import SwiftUI

@MainActor
final class AppModel: ObservableObject {
    enum Screen {
        case start
        case capture
        case review(CapturedScan)
        case upload(UploadViewModel)
        case workspace(UUID)
        case connection
    }

    @Published var screen: Screen = .start
    @Published private(set) var savedScans = CaptureLibrary.all()
    @Published private(set) var captureSessionID = UUID()
    @Published var workspaceSession: WebSession?
    @Published private(set) var recoveryDirectories: [URL] = []
    @Published private(set) var recoveryMessage: String?
    private var uploads: [UUID: UploadViewModel] = [:]

    func beginCapture() {
        captureSessionID = UUID()
        screen = .capture
    }

    func showStart() {
        savedScans = CaptureLibrary.all()
        screen = .start
    }

    func connectionChanged() {
        uploads.values.forEach { $0.cancel() }
        uploads.removeAll()
        workspaceSession = nil
        showStart()
    }

    func recoverSavedRoom(_ directory: URL) async {
        recoveryMessage = "Saving your room"
        let result = await Task.detached(priority: .userInitiated) {
            Result { try CaptureRecovery.recover(from: directory) }
        }.value
        switch result {
        case .success(let scan):
            recoveryMessage = nil
            recoveryDirectories.removeAll { $0 == directory }
            screen = .review(scan)
        case .failure: recoveryMessage = "Free some space on this phone, then save again."
        }
    }

    func upload(scan: CapturedScan, name: String) {
        guard let baseURL = AppEnvironment.apiBaseURL else {
            screen = .connection
            return
        }
        if let existing = uploads[scan.id] {
            screen = .upload(existing)
            return
        }
        let model = UploadViewModel(
            scan: scan,
            name: name,
            client: ScanUploadClient(baseURL: baseURL)
        )
        uploads[scan.id] = model
        model.start()
        screen = .upload(model)
    }

    func refreshSavedScanStates() async {
        if let root = try? FileManager.default.url(for: .applicationSupportDirectory,
            in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("Captures") {
            recoveryDirectories = CaptureRecovery.directories(in: root)
        }
        while !Task.isCancelled {
            for scan in savedScans {
                let store = ResumableUploadStore(captureDirectory: scan.directory)
                guard store.scanID != nil, uploads[scan.id] == nil,
                      let baseURL = AppEnvironment.apiBaseURL else { continue }
                let model = UploadViewModel(scan: scan, name: scan.name ?? "Shop scan",
                    client: ScanUploadClient(baseURL: baseURL))
                uploads[scan.id] = model
                model.start()
            }
            savedScans = CaptureLibrary.all()
            do { try await Task.sleep(for: .seconds(2)) } catch { return }
        }
    }
}

struct AppRootView: View {
    @StateObject private var model = AppModel()

    var body: some View {
        Group {
            if DeviceSupport.canCaptureRooms {
                SupportedAppView(model: model)
            } else {
                UnsupportedDeviceView()
            }
        }
        .tint(AppTheme.accent)
        .preferredColorScheme(.light)
    }
}

private enum DeviceSupport {
    static var canCaptureRooms: Bool {
#if targetEnvironment(simulator)
        if ProcessInfo.processInfo.environment["SIMULATOR_CAPTURE_DEMO"] == "1" { return true }
#endif
        return RoomCaptureSession.isSupported
    }
}

private struct SupportedAppView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        switch model.screen {
        case .start:
            StartView(model: model)
        case .capture:
            CaptureScreen(model: model)
                .id(model.captureSessionID)
        case .review(let scan):
            ReviewScreen(model: model, scan: scan)
        case .upload(let uploadModel):
            UploadStatusScreen(appModel: model, uploadModel: uploadModel)
        case .workspace(let scanID):
            WorkspaceScreen(appModel: model, scanID: scanID)
        case .connection:
            ConnectionScreen(model: model)
        }
    }
}

private struct StartView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.canvas.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.page) {
                        Spacer(minLength: 64)
                        Image(systemName: "viewfinder")
                            .font(.system(size: 54, weight: .light))
                            .foregroundStyle(AppTheme.accent)
                            .accessibilityHidden(true)
                        Text("Measure your shop")
                            .font(AppTheme.Typography.hero)
                            .foregroundStyle(AppTheme.ink)
                        Text("Walk once around the room. We’ll show you where to point.")
                            .font(.title3)
                            .foregroundStyle(AppTheme.mutedInk)
                        Button("Start scanning") { model.beginCapture() }
                            .buttonStyle(AppButtonStyle())
                        Button("Connection") { model.screen = .connection }
                            .buttonStyle(AppButtonStyle(.secondary))
                        if !model.savedScans.isEmpty {
                            SavedScansView(scans: model.savedScans) { model.screen = .review($0) }
                        }
                        ForEach(model.recoveryDirectories, id: \.self) { directory in
                            Button("Recover saved room") {
                                Task { await model.recoverSavedRoom(directory) }
                            }.buttonStyle(AppButtonStyle(.secondary))
                        }
                        if let message = model.recoveryMessage { Text(message) }
                    }
                    .padding(AppTheme.Spacing.page)
                }
            }
            .toolbar(.hidden, for: .navigationBar)
            .task { await model.refreshSavedScanStates() }
        }
    }
}

private struct SavedScansView: View {
    let scans: [CapturedScan]
    let select: (CapturedScan) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.small) {
            Text("Saved scans")
                .font(.title2.bold())
            ForEach(scans) { scan in
                Button { select(scan) } label: {
                    HStack(spacing: AppTheme.Spacing.compact) {
                        Image(systemName: "cube.transparent")
                            .font(.title2)
                            .foregroundStyle(AppTheme.accent)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(scan.name ?? "Shop scan")
                                .font(.headline)
                            Text(ResumableUploadStore(captureDirectory: scan.directory).historyText)
                                .font(.subheadline)
                                .foregroundStyle(AppTheme.mutedInk)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .foregroundStyle(.secondary)
                    }
                    .padding(AppTheme.Spacing.card)
                    .background(AppTheme.panel)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.top, AppTheme.Spacing.compact)
    }
}

private struct UnsupportedDeviceView: View {
    var body: some View {
        ZStack {
            AppTheme.canvas.ignoresSafeArea()
            Text("Use an iPhone Pro or Pro Max with LiDAR (12 or later), or an iPad Pro with LiDAR (2020 or later).")
                .font(.title2.weight(.semibold))
                .foregroundStyle(AppTheme.ink)
                .multilineTextAlignment(.center)
                .padding(AppTheme.Spacing.page)
        }
    }
}
