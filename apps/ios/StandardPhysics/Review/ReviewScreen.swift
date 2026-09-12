import SceneKit
import SwiftUI

struct ReviewScreen: View {
    @ObservedObject var model: AppModel
    let scan: CapturedScan
    @State private var name: String
    @State private var showDetail = true
    @State private var roomScene: SCNScene?
    @State private var detailScene: SCNScene?
    @State private var saveError: String?

    init(model: AppModel, scan: CapturedScan) {
        self.model = model
        self.scan = scan
        _name = State(initialValue: scan.name ?? "")
    }

    var body: some View {
        ZStack {
            AppTheme.canvas.ignoresSafeArea()
            VStack(spacing: 0) {
                ZStack(alignment: .topLeading) {
                    SceneView(
                        scene: showDetail ? detailScene ?? roomScene : roomScene,
                        options: [.allowsCameraControl, .autoenablesDefaultLighting]
                    )
                    .background(AppTheme.panel)
                    Button {
                        model.showStart()
                    } label: {
                        Image(systemName: "chevron.left")
                            .font(.headline)
                            .frame(width: AppTheme.Size.touchTarget, height: AppTheme.Size.touchTarget)
                            .background(AppTheme.panel)
                            .clipShape(Circle())
                            .shadow(
                                color: AppTheme.Shadow.color,
                                radius: AppTheme.Shadow.radius,
                                y: AppTheme.Shadow.y
                            )
                    }
                    .foregroundStyle(AppTheme.ink)
                    .padding(AppTheme.Spacing.card)
                    .accessibilityLabel("Back")
                }

                VStack(alignment: .leading, spacing: AppTheme.Spacing.card) {
                    if let notice = scan.captureNotice {
                        Text(notice).foregroundStyle(AppTheme.mutedInk)
                        Button("Record another pass") { model.beginCapture() }
                            .buttonStyle(AppButtonStyle(.secondary))
                    }
                    if detailScene != nil {
                        Picker("Room view", selection: $showDetail) {
                            Text("Details").tag(true)
                            Text("Room layout").tag(false)
                        }.pickerStyle(.segmented)
                        ShareLink("Share detailed scan", item: scan.directory.appendingPathComponent("lidar-mesh.json"))
                    }
                    Text("Name this shop")
                        .font(.title2.bold())
                    TextField("Boba shop", text: $name)
                        .textInputAutocapitalization(.words)
                        .font(.title3)
                        .padding(AppTheme.Spacing.control)
                        .background(AppTheme.panel)
                        .overlay {
                            RoundedRectangle(cornerRadius: AppTheme.Radius.field, style: .continuous)
                                .stroke(AppTheme.fieldOutline, lineWidth: 1)
                        }
                    Button("Upload scan") {
                        do {
                            model.upload(scan: try scan.renamed(trimmedName), name: trimmedName)
                        } catch { saveError = "Free some space on this phone, then save again." }
                    }
                    .buttonStyle(AppButtonStyle())
                    .disabled(trimmedName.isEmpty)
                    if let saveError { Text(saveError).foregroundStyle(AppTheme.warning) }
                }
                .padding(AppTheme.Spacing.section)
            }
        }
        .task(id: scan.id) {
            roomScene = try? SCNScene(url: scan.roomURL)
            detailScene = try? LidarMesh.load(from: scan.directory).makeScene()
        }
    }

    private var trimmedName: String {
        name.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
