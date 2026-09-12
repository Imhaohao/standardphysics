import RoomPlan
import SwiftUI

@MainActor
final class AppModel: ObservableObject {
    enum Screen {
        case start
        case capture
        case review(CapturedScan)
        case upload(UploadViewModel)
        case workspace(String)
    }

    @Published var screen: Screen = .start
    @Published private(set) var savedScans = CaptureLibrary.all()

    func showStart() {
        savedScans = CaptureLibrary.all()
        screen = .start
    }

    func upload(scan: CapturedScan, name: String) {
        let model = UploadViewModel(
            scan: scan,
            name: name,
            client: ScanUploadClient(baseURL: AppEnvironment.apiBaseURL)
        )
        screen = .upload(model)
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
        case .review(let scan):
            ReviewScreen(model: model, scan: scan)
        case .upload(let uploadModel):
            UploadStatusScreen(appModel: model, uploadModel: uploadModel)
        case .workspace(let scanID):
            WorkspaceScreen(appModel: model, scanID: scanID)
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
                    VStack(alignment: .leading, spacing: 28) {
                        Spacer(minLength: 64)
                        Image(systemName: "viewfinder")
                            .font(.system(size: 54, weight: .light))
                            .foregroundStyle(AppTheme.accent)
                            .accessibilityHidden(true)
                        Text("Measure your shop")
                            .font(.system(size: 50, weight: .bold, design: .rounded))
                            .foregroundStyle(AppTheme.ink)
                        Text("Walk once around the room. We’ll show you where to point.")
                            .font(.title3)
                            .foregroundStyle(AppTheme.mutedInk)
                        Button("Start scanning") { model.screen = .capture }
                            .buttonStyle(PrimaryButtonStyle())
                        if !model.savedScans.isEmpty {
                            SavedScansView(scans: model.savedScans) { model.screen = .review($0) }
                        }
                    }
                    .padding(28)
                }
            }
            .toolbar(.hidden, for: .navigationBar)
        }
    }
}

private struct SavedScansView: View {
    let scans: [CapturedScan]
    let select: (CapturedScan) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Saved scans")
                .font(.title2.bold())
            ForEach(scans) { scan in
                Button { select(scan) } label: {
                    HStack(spacing: 14) {
                        Image(systemName: "cube.transparent")
                            .font(.title2)
                            .foregroundStyle(AppTheme.accent)
                        Text(scan.name ?? "Shop scan")
                            .font(.headline)
                        Spacer()
                        Image(systemName: "chevron.right")
                            .foregroundStyle(.secondary)
                    }
                    .padding(18)
                    .background(AppTheme.panel)
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.top, 14)
    }
}

private struct UnsupportedDeviceView: View {
    var body: some View {
        ZStack {
            AppTheme.canvas.ignoresSafeArea()
            Text("Use an iPhone 12 Pro or newer, or an iPad Pro from 2020 or newer.")
                .font(.title2.weight(.semibold))
                .foregroundStyle(AppTheme.ink)
                .multilineTextAlignment(.center)
                .padding(32)
        }
    }
}
