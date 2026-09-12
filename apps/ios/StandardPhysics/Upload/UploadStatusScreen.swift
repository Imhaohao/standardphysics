import SwiftUI

struct UploadStatusScreen: View {
    @ObservedObject var appModel: AppModel
    @ObservedObject var uploadModel: UploadViewModel

    var body: some View {
        ZStack {
            AppTheme.canvas.ignoresSafeArea()
            VStack(spacing: 28) {
                Spacer()
                statusMark
                Text(uploadModel.state.displayText)
                    .font(.system(size: 38, weight: .bold, design: .rounded))
                    .multilineTextAlignment(.center)
                if let message = uploadModel.errorMessage {
                    Text(message)
                        .font(.body)
                        .foregroundStyle(AppTheme.mutedInk)
                        .multilineTextAlignment(.center)
                }
                Spacer()
                actions
            }
            .padding(28)
        }
        .task { uploadModel.start() }
        .onDisappear { uploadModel.cancel() }
    }

    @ViewBuilder private var statusMark: some View {
        if uploadModel.state == .ready {
            Image(systemName: "checkmark")
                .font(.system(size: 38, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: 82, height: 82)
                .background(AppTheme.accent)
                .clipShape(Circle())
                .accessibilityHidden(true)
        } else {
            ProgressView()
                .controlSize(.large)
                .tint(AppTheme.accent)
                .frame(width: 82, height: 82)
        }
    }

    @ViewBuilder private var actions: some View {
        if uploadModel.state == .ready, let scanID = uploadModel.scanID {
            Button("Open your shop") { appModel.screen = .workspace(scanID) }
                .buttonStyle(PrimaryButtonStyle())
        } else if uploadModel.errorMessage != nil {
            Button("Try again") { uploadModel.retry() }
                .buttonStyle(PrimaryButtonStyle())
            Button("Back to saved scans") { appModel.showStart() }
                .buttonStyle(SecondaryButtonStyle())
        }
    }
}
