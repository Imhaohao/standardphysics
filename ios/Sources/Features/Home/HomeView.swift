import SwiftUI

struct HomeView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ZStack {
            PaperBackground()
            SheetFrame {
                ScrollView {
                    VStack(alignment: .leading, spacing: Theme.Spacing.xl) {
                        InkedTitle(text: "Your scans")
                        content
                    }
                    .padding(Theme.Spacing.m)
                    .padding(.top, Theme.Spacing.s)
                }
                .scrollIndicators(.hidden)
                .safeAreaInset(edge: .bottom) { startButton }
            }
            .padding(.horizontal, Theme.Spacing.s)
            .padding(.vertical, Theme.Spacing.xs)
        }
        .task { await model.refresh() }
    }

    @ViewBuilder private var content: some View {
        if model.unfinishedScans.isEmpty && model.reports.isEmpty {
            HomeEmptyState()
        }
        if !model.unfinishedScans.isEmpty {
            HomeSection(title: "Unfinished") {
                ForEach(model.unfinishedScans, id: \.scanID) { scan in
                    UnfinishedScanCard(scan: scan) {
                        Task { await model.continueScan(scan.scanID) }
                    }
                }
            }
        }
        if !model.reports.isEmpty {
            HomeSection(title: "Checked") {
                ForEach(model.reports) { report in
                    ReportRow(report: report) { model.openReport(report.scanID) }
                }
            }
        }
    }

    private var startButton: some View {
        Group {
            if model.unfinishedScans.isEmpty {
                PrimaryButton(title: "Start a new scan", systemImage: "viewfinder") { model.startNewScan() }
            } else {
                SecondaryButton(title: "Start a new scan", systemImage: "plus") { model.startNewScan() }
            }
        }
        .padding(Theme.Spacing.m)
        .background(Theme.Palette.paper.opacity(0.92))
    }
}

/// A display heading with the brush underline inking itself beneath it.
struct InkedTitle: View {
    let text: String
    var color: Color = Theme.Palette.ink

    var body: some View {
        Text(text)
            .font(Theme.Typography.display)
            .foregroundStyle(Theme.Palette.ink)
            .accessibilityAddTraits(.isHeader)
            .padding(.bottom, Theme.Spacing.s)
            .background(alignment: .bottomLeading) {
                InkStroke(weight: Theme.Stroke.inkBold, color: color)
                    .frame(height: 16)
                    .offset(x: -4, y: 6)
            }
    }
}

private struct HomeSection<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s + 4) {
            Text(title)
                .font(Theme.Typography.title)
                .foregroundStyle(Theme.Palette.ink)
                .accessibilityAddTraits(.isHeader)
            content
        }
    }
}

private struct UnfinishedScanCard: View {
    let scan: ScanManifest
    let onContinue: () -> Void

    var body: some View {
        Card(variant: .raised) {
            VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text(scan.name)
                        .font(Theme.Typography.title)
                        .foregroundStyle(Theme.Palette.ink)
                    Text(savedLine)
                        .font(Theme.Typography.callout)
                        .foregroundStyle(Theme.Palette.inkMuted)
                }
                RoomSlots(saved: scan.rooms.count)
                PrimaryButton(title: "Continue scanning", systemImage: "arrow.forward", action: onContinue)
            }
        }
    }

    private var savedLine: String {
        let rooms = scan.rooms.count == 1 ? "1 room saved" : "\(scan.rooms.count) rooms saved"
        let when = (scan.worldMapSavedAt ?? scan.startedAt).formatted(.relative(presentation: .named))
        return "\(rooms), last saved \(when)"
    }
}

/// One square per room a scan can hold; saved rooms are inked in.
struct RoomSlots: View {
    let saved: Int

    var body: some View {
        HStack(spacing: Theme.Spacing.xs + 2) {
            ForEach(1...ScanLimits.maxRooms, id: \.self) { index in
                Rectangle()
                    .fill(index <= saved ? Theme.Palette.ink : Theme.Palette.gridMajor)
                    .frame(width: 22, height: 22)
                    .overlay {
                        if index == saved + 1 {
                            Rectangle().stroke(Theme.Palette.ink, style: StrokeStyle(lineWidth: 1.5, dash: [3, 2]))
                        }
                    }
            }
        }
        .accessibilityElement()
        .accessibilityLabel("\(saved) of \(ScanLimits.maxRooms) rooms used")
    }
}

private struct ReportRow: View {
    let report: ScanReport
    let action: () -> Void

    var body: some View {
        let summary = ReportGrouping.summary(for: report)
        Button(action: action) {
            Card {
                HStack(spacing: Theme.Spacing.m) {
                    VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                        Text(report.name)
                            .font(Theme.Typography.headline)
                            .foregroundStyle(Theme.Palette.ink)
                        Text(report.completedAt.formatted(date: .abbreviated, time: .omitted))
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Palette.inkMuted)
                    }
                    Spacer(minLength: Theme.Spacing.s)
                    if summary.toFix > 0 {
                        StatusPill(tone: .fail, title: "\(summary.toFix) to fix")
                    } else {
                        StatusPill(tone: .pass, title: "Nothing to fix")
                    }
                    Image(systemName: "chevron.right")
                        .font(Theme.Typography.caption.weight(.bold))
                        .foregroundStyle(Theme.Palette.inkFaint)
                }
            }
        }
        .buttonStyle(.plain)
    }
}

private struct HomeEmptyState: View {
    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            Text("No scans yet")
                .font(Theme.Typography.title)
                .foregroundStyle(Theme.Palette.ink)
            Text("Walk through your space with this iPhone. We'll measure doors, counters, aisles and restrooms, then show you what to fix under ADA and California rules.")
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Palette.inkMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
