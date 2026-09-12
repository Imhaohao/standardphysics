import SceneKit
import SwiftUI

struct ReviewScreen: View {
    @ObservedObject var model: AppModel
    let scan: CapturedScan
    @State private var name: String

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
                        scene: try? SCNScene(url: scan.roomURL),
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
                        model.upload(scan: scan.renamed(trimmedName), name: trimmedName)
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(trimmedName.isEmpty)
                    .opacity(trimmedName.isEmpty ? 0.45 : 1)
                }
                .padding(AppTheme.Spacing.section)
            }
        }
    }

    private var trimmedName: String {
        name.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
