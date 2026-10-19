import AVFoundation
import SwiftUI

struct BeforeYouScanView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openURL) private var openURL
    @State private var camera = CameraPermission()
    @State private var placeName = ""
    @FocusState private var isNameFocused: Bool

    private let steps = [
        "Start at the door and walk slowly along the edges of the room.",
        "Point the camera at doors, counters, shelves and restroom fixtures as you pass them.",
        "When the room looks complete, tap Finish room. One scan can hold up to \(ScanLimits.maxRooms) rooms.",
        "If something interrupts you, the scan pauses and keeps everything you've done.",
    ]

    var body: some View {
        ZStack {
            PaperBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                    BackButton(title: "Your scans") { model.goHome() }
                    InkedTitle(text: "Before you scan")
                    ChestHeightDiagram()
                    StepList(steps: steps)
                    nameField
                    Text("Each room takes a minute or two. After you finish, checking every rule takes up to a minute.")
                        .font(Theme.Typography.callout)
                        .foregroundStyle(Theme.Palette.inkMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(Theme.Spacing.m)
                .frame(maxWidth: Theme.Size.readable, alignment: .leading)
            }
            .scrollDismissesKeyboard(.interactively)
            .safeAreaInset(edge: .bottom) { actions }
        }
    }

    private var nameField: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            Text("What's this place called?")
                .font(Theme.Typography.headline)
                .foregroundStyle(Theme.Palette.ink)
            TextField("Hollis Street Bakery", text: $placeName)
                .font(Theme.Typography.body)
                .textContentType(.organizationName)
                .submitLabel(.done)
                .focused($isNameFocused)
                .padding(.horizontal, Theme.Spacing.m)
                .frame(minHeight: Theme.Size.control)
                .background(RoundedRectangle(cornerRadius: Theme.Radius.control).fill(Theme.Palette.sheet))
                .overlay(RoundedRectangle(cornerRadius: Theme.Radius.control).stroke(Theme.Palette.rule, lineWidth: Theme.Stroke.hairline))
        }
    }

    @ViewBuilder private var actions: some View {
        VStack(spacing: Theme.Spacing.s) {
            if camera.status == .denied {
                CameraDeniedNote { openSettings() }
            } else {
                PrimaryButton(title: camera.status == .authorized ? "Start scanning" : "Allow camera and start", systemImage: "viewfinder") {
                    Task { await start() }
                }
            }
        }
        .padding(Theme.Spacing.m)
        .background(Theme.Palette.paper)
    }

    private func start() async {
        isNameFocused = false
        guard await camera.request() else { return }
        await model.beginScanning(name: placeName)
    }

    private func openSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        openURL(url)
    }
}

@Observable
final class CameraPermission {
    enum Status {
        case notDetermined
        case authorized
        case denied
    }

    private(set) var status: Status

    init() {
        status = Self.current()
    }

    func request() async -> Bool {
        if status == .notDetermined {
            _ = await AVCaptureDevice.requestAccess(for: .video)
            status = Self.current()
        }
        return status == .authorized
    }

    private static func current() -> Status {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: .authorized
        case .notDetermined: .notDetermined
        default: .denied
        }
    }
}

private struct CameraDeniedNote: View {
    let openSettings: () -> Void

    var body: some View {
        Card(variant: .raised) {
            VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                Label("Camera access is off for Standard Physics. Turn it on in Settings to scan.", systemImage: "camera.fill")
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Palette.ink)
                PrimaryButton(title: "Open Settings", systemImage: "gear", action: openSettings)
            }
        }
    }
}

private struct StepList: View {
    let steps: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.m) {
                    Text("\(index + 1)")
                        .font(Theme.Typography.headline)
                        .foregroundStyle(Theme.Palette.accent)
                        .frame(width: 18, alignment: .leading)
                    Text(step)
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Palette.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

struct BackButton: View {
    let title: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label(title, systemImage: "chevron.left")
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Palette.accent)
                .frame(minHeight: Theme.Size.compactControl)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// Side view of the scanning posture: the phone at chest height, its view reaching the far wall.
private struct ChestHeightDiagram: View {
    private let chestHeight: CGFloat = 92

    var body: some View {
        Card(variant: .sheet, padding: Theme.Spacing.m) {
            VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                Canvas { context, size in draw(in: &context, size: size) }
                    .frame(height: 132)
                    .overlay(alignment: .topLeading) { labels }
                    .accessibilityHidden(true)
                Text("Hold the phone upright at chest height, about 4 ft up, so it sees counters, door handles and the floor in one view.")
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Palette.inkMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var labels: some View {
        GeometryReader { proxy in
            let floorY = proxy.size.height - 10
            Image(systemName: "iphone.gen3")
                .font(.system(size: 24))
                .foregroundStyle(Theme.Palette.ink)
                .position(x: 74, y: floorY - chestHeight)
            MeasurementText(text: "4 ft", size: .small, color: Theme.Palette.ink)
                .fixedSize()
                .position(x: 40, y: floorY - chestHeight / 2)
        }
    }

    private func draw(in context: inout GraphicsContext, size: CGSize) {
        let floorY = size.height - 10
        let phone = CGPoint(x: 86, y: floorY - chestHeight)
        let wallX = size.width - 6
        var cone = Path()
        cone.move(to: phone)
        cone.addLine(to: CGPoint(x: wallX, y: phone.y - 58))
        cone.addLine(to: CGPoint(x: wallX, y: floorY))
        cone.closeSubpath()
        context.fill(cone, with: .color(Theme.Palette.accent.opacity(0.14)))
        let line = InkBrushStyle(weight: Theme.Stroke.inkFine * 1.4, seed: 5, pooledStart: false)
        InkBrush.draw(points: [CGPoint(x: 0, y: floorY), CGPoint(x: size.width, y: floorY)], progress: 1, style: line, color: Theme.Palette.ink, in: &context)
        InkBrush.draw(points: [CGPoint(x: wallX, y: floorY), CGPoint(x: wallX, y: 0)], progress: 1, style: InkBrushStyle(weight: Theme.Stroke.inkFine * 1.4, seed: 9, pooledStart: false), color: Theme.Palette.ink, in: &context)
        drawDimension(from: floorY, to: phone.y, x: 16, in: &context)
    }

    private func drawDimension(from bottom: CGFloat, to top: CGFloat, x: CGFloat, in context: inout GraphicsContext) {
        let fine = InkBrushStyle(weight: Theme.Stroke.inkFine, seed: 13, fiberChance: 0.04, pooledStart: false)
        InkBrush.draw(points: [CGPoint(x: x, y: bottom), CGPoint(x: x, y: top)], progress: 1, style: fine, color: Theme.Palette.ink, in: &context)
        for y in [bottom, top] {
            let slash = [CGPoint(x: x - 5, y: y + 5), CGPoint(x: x + 5, y: y - 5)]
            InkBrush.draw(points: slash, progress: 1, style: fine, color: Theme.Palette.ink, in: &context)
        }
        InkBrush.draw(points: [CGPoint(x: x - 6, y: top), CGPoint(x: 62, y: top)], progress: 1, style: InkBrushStyle(weight: 1, seed: 3, fiberChance: 0, pooledStart: false), color: Theme.Palette.ink.opacity(0.5), in: &context)
    }
}
