import SwiftUI

/// A Liquid Glass panel for text over the camera. Controls inside switch to their camera look.
struct HUDPanel<Content: View>: View {
    var padding: CGFloat = Theme.Spacing.m
    @ViewBuilder let content: Content

    var body: some View {
        content
            .foregroundStyle(Theme.Palette.sheet)
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glassEffect(.regular.tint(Theme.Palette.camera.opacity(0.45)), in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            .environment(\.controlSurface, .camera)
    }
}

struct HUDCapsule<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        content
            .font(Theme.Typography.callout)
            .foregroundStyle(Theme.Palette.sheet)
            .padding(.horizontal, Theme.Spacing.m)
            .frame(minHeight: Theme.Size.compactControl)
            .glassEffect(.regular.tint(Theme.Palette.camera.opacity(0.45)), in: Capsule())
    }
}

struct LeaveScanButton: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: "xmark")
                .font(Theme.Typography.headline)
                .foregroundStyle(Theme.Palette.sheet)
                .frame(width: Theme.Size.compactControl, height: Theme.Size.compactControl)
        }
        .glassEffect(.regular.tint(Theme.Palette.camera.opacity(0.45)).interactive(), in: Circle())
        .accessibilityLabel("Leave scan")
    }
}

struct CaptureTopBar: View {
    let room: Int
    let onLeave: () -> Void

    var body: some View {
        HStack {
            HUDCapsule {
                HStack(spacing: Theme.Spacing.s) {
                    Text("Room \(room)").font(Theme.Typography.headline)
                    Text("of up to \(ScanLimits.maxRooms)").foregroundStyle(Theme.Palette.sheet.opacity(0.7))
                }
            }
            Spacer()
            LeaveScanButton(action: onLeave)
        }
    }
}
