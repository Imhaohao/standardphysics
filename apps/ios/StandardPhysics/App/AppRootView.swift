import RoomPlan
import SwiftUI

struct AppRootView: View {
    var body: some View {
        Group {
            if RoomCaptureSession.isSupported {
                StartView()
            } else {
                UnsupportedDeviceView()
            }
        }
        .preferredColorScheme(.light)
    }
}

private struct StartView: View {
    var body: some View {
        ZStack {
            Color(red: 0.95, green: 0.94, blue: 0.90).ignoresSafeArea()
            VStack(alignment: .leading, spacing: 24) {
                Spacer()
                Text("Measure your shop")
                    .font(.system(size: 50, weight: .bold, design: .rounded))
                Text("Walk once around the room. We’ll show you where to point.")
                    .font(.title3)
                    .foregroundStyle(.secondary)
                Button("Start scanning") {}
                    .buttonStyle(PrimaryButtonStyle())
            }
            .padding(28)
        }
    }
}

private struct UnsupportedDeviceView: View {
    var body: some View {
        ZStack {
            Color(red: 0.95, green: 0.94, blue: 0.90).ignoresSafeArea()
            Text("Use an iPhone 12 Pro or newer, or an iPad Pro from 2020 or newer.")
                .font(.title2.weight(.semibold))
                .multilineTextAlignment(.center)
                .padding(32)
        }
    }
}

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 17)
            .foregroundStyle(.white)
            .background(configuration.isPressed ? Color.black.opacity(0.78) : .black)
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}
