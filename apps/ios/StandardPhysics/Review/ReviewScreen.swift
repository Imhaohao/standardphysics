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
                    .background(Color.white)
                    Button {
                        model.showStart()
                    } label: {
                        Image(systemName: "chevron.left")
                            .font(.headline)
                            .frame(width: 44, height: 44)
                            .background(AppTheme.panel)
                            .clipShape(Circle())
                            .shadow(color: .black.opacity(0.12), radius: 12, y: 5)
                    }
                    .foregroundStyle(AppTheme.ink)
                    .padding(18)
                    .accessibilityLabel("Back")
                }

                VStack(alignment: .leading, spacing: 18) {
                    Text("Name this shop")
                        .font(.title2.bold())
                    TextField("Boba shop", text: $name)
                        .textInputAutocapitalization(.words)
                        .font(.title3)
                        .padding(16)
                        .background(.white)
                        .overlay {
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .stroke(Color.black.opacity(0.14), lineWidth: 1)
                        }
                    Button("Upload scan") {
                        model.upload(scan: scan.renamed(trimmedName), name: trimmedName)
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(trimmedName.isEmpty)
                    .opacity(trimmedName.isEmpty ? 0.45 : 1)
                }
                .padding(24)
            }
        }
    }

    private var trimmedName: String {
        name.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
