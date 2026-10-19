import SwiftUI

/// The drawing-sheet border from the web homepage: a heavy outer line, a fine inner line and
/// zone bands numbered along the top and bottom and lettered down the sides.
struct SheetFrame<Content: View>: View {
    var columns = 4
    var rows = 6
    @ViewBuilder let content: Content

    var body: some View {
        let band = Theme.Size.zoneBand
        VStack(spacing: 0) {
            ZoneBand(labels: columnLabels, axis: .horizontal).frame(height: band).padding(.horizontal, band)
            HStack(spacing: 0) {
                ZoneBand(labels: rowLabels, axis: .vertical).frame(width: band)
                content
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .overlay(Rectangle().stroke(Theme.Palette.ink, lineWidth: Theme.Stroke.hairline))
                ZoneBand(labels: rowLabels, axis: .vertical).frame(width: band)
            }
            ZoneBand(labels: columnLabels, axis: .horizontal).frame(height: band).padding(.horizontal, band)
        }
        .overlay(Rectangle().stroke(Theme.Palette.ink, lineWidth: Theme.Stroke.frame))
    }

    private var columnLabels: [String] {
        (1...columns).map(String.init)
    }

    private var rowLabels: [String] {
        (0..<rows).map { String(UnicodeScalar(UInt8(65 + $0))) }
    }
}

private struct ZoneBand: View {
    let labels: [String]
    let axis: Axis

    var body: some View {
        let layout = axis == .horizontal ? AnyLayout(HStackLayout(spacing: 0)) : AnyLayout(VStackLayout(spacing: 0))
        layout {
            ForEach(Array(labels.enumerated()), id: \.offset) { index, label in
                Text(label)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Palette.inkFaint)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .overlay(alignment: axis == .horizontal ? .leading : .top) {
                        if index > 0 { divider }
                    }
            }
        }
        .accessibilityHidden(true)
    }

    @ViewBuilder private var divider: some View {
        let tick = Theme.Palette.ink.opacity(0.4)
        if axis == .horizontal {
            Rectangle().fill(tick).frame(width: Theme.Stroke.hairline)
        } else {
            Rectangle().fill(tick).frame(height: Theme.Stroke.hairline)
        }
    }
}

#Preview {
    SheetFrame {
        Text("Your scans").font(Theme.Typography.display)
    }
    .padding()
    .background(PaperBackground())
}
