import SwiftUI

@main
struct StandardPhysicsApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
                .tint(Theme.Palette.accent)
        }
    }
}

struct RootView: View {
    var body: some View {
        ZStack {
            Theme.Palette.paper.ignoresSafeArea()
            Text("Standard Physics")
                .font(Theme.Typography.display)
                .foregroundStyle(Theme.Palette.ink)
        }
    }
}
