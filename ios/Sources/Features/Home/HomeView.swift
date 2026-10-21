import SwiftUI

struct HomeView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ZStack {
            PaperBackground()
            SheetFrame {
                ScrollView {
                    VStack(alignment: .leading, spacing: Theme.Spacing.xl) {
                        HomeHeader(account: model.account)
                        content
                    }
                    .padding(Theme.Spacing.m)
                    .padding(.top, Theme.Spacing.s)
                }
                .scrollIndicators(.hidden)
                .safeAreaInset(edge: .bottom) {
                    if model.canScan { startButton }
                }
            }
            .padding(.horizontal, Theme.Spacing.s)
            .padding(.vertical, Theme.Spacing.xs)
        }
        .task { await model.refresh() }
        .onChange(of: model.account.state) { _, _ in
            Task { await model.refresh() }
        }
        .sheet(isPresented: Bindable(model.account).isSheetPresented) {
            AccountSheet(account: model.account)
                .presentationDetents([.large])
        }
    }

    @ViewBuilder private var content: some View {
        if let notice = model.notice {
            NoticeBanner(message: notice) { model.dismissNotice() }
        }
        if !model.canScan {
            UnsupportedPhoneNotice(account: model.account)
        } else if model.unfinishedScans.isEmpty && model.reports.isEmpty {
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
                    ReportRow(report: report)
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

/// The title, and who is signed in. Signed out, the button offers sign-in; signed in, it shows
/// the account the scans go to.
private struct HomeHeader: View {
    let account: AccountModel

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            HStack(alignment: .top) {
                InkedTitle(text: "Your scans")
                Spacer(minLength: Theme.Spacing.s)
                if account.isAvailable {
                    Button { account.isSheetPresented = true } label: {
                        ButtonLabel(
                            title: account.state.isSignedIn ? "Account" : "Sign in",
                            systemImage: account.state.isSignedIn ? "person.crop.circle.fill" : "person.crop.circle"
                        )
                    }
                    .buttonStyle(InkButtonStyle(variant: .quiet, height: Theme.Size.compactControl))
                }
            }
            if case .signedIn(let email) = account.state {
                Label(email.map { "Signed in as \($0)" } ?? "Signed in with Apple", systemImage: "checkmark.icloud")
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Palette.inkMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
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
    @Environment(AppModel.self) private var model
    let scan: ScanManifest
    let onContinue: () -> Void
    @State private var isConfirmingDelete = false

    var body: some View {
        card
            .contextMenu {
                Button("Delete scan", systemImage: "trash", role: .destructive) { isConfirmingDelete = true }
            }
            .alert("Delete this scan?", isPresented: $isConfirmingDelete) {
                Button("Delete scan", role: .destructive) {
                    Task { await model.deleteUnfinishedScan(scan.scanID) }
                }
                Button("Keep it", role: .cancel) {}
            } message: {
                Text(HomeCopy.deleteScanMessage(scan))
            }
    }

    private var card: some View {
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

/// Opens the report on tap; a long press offers rename and delete.
private struct ReportRow: View {
    @Environment(AppModel.self) private var model
    let report: ScanReport
    @State private var isRenaming = false
    @State private var draftName = ""
    @State private var isConfirmingDelete = false

    var body: some View {
        Button { model.openReport(report.scanID) } label: { ReportRowLabel(report: report) }
            .buttonStyle(.plain)
            .contextMenu {
                Button("Rename", systemImage: "pencil") {
                    draftName = report.name
                    isRenaming = true
                }
                Button("Delete report", systemImage: "trash", role: .destructive) { isConfirmingDelete = true }
            }
            .alert("Rename this report", isPresented: $isRenaming) {
                TextField("Report name", text: $draftName)
                Button("Save") {
                    let name = draftName
                    Task { await model.renameReport(report.scanID, to: name) }
                }
                Button("Cancel", role: .cancel) {}
            }
            .alert("Delete this report?", isPresented: $isConfirmingDelete) {
                Button("Delete report", role: .destructive) {
                    Task { await model.deleteReport(report.scanID) }
                }
                Button("Keep it", role: .cancel) {}
            } message: {
                Text(HomeCopy.deleteReportMessage(report))
            }
    }
}

nonisolated enum HomeCopy {
    static func deleteReportMessage(_ report: ScanReport) -> String {
        guard report.remoteScanID != nil else {
            return "“\(report.name)” and the rooms behind it will be removed from this phone. You can't undo this."
        }
        return "“\(report.name)” will be removed from this phone and from your Standard Physics account. You can't undo this."
    }

    static func deleteScanMessage(_ scan: ScanManifest) -> String {
        let rooms = scan.rooms.count == 1 ? "1 saved room" : "\(scan.rooms.count) saved rooms"
        return "“\(scan.name)” and its \(rooms) will be removed from this phone. You can't undo this."
    }
}

private struct ReportRowLabel: View {
    let report: ScanReport

    var body: some View {
        let summary = ReportGrouping.summary(for: report)
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
}

/// Shown instead of "Start a new scan" on a phone without LiDAR. Signing in still brings in the
/// reports from scans made on another phone.
private struct UnsupportedPhoneNotice: View {
    let account: AccountModel

    var body: some View {
        Card(variant: .raised) {
            VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                Label("This iPhone can't scan", systemImage: "iphone.slash")
                    .font(Theme.Typography.title)
                    .foregroundStyle(Theme.Palette.ink)
                Text("Scanning measures your space with the LiDAR sensor, which only iPhone Pro and Pro Max models from iPhone 12 Pro onward have. This phone doesn't have one, so it can't start a scan.")
                    .font(Theme.Typography.body)
                    .foregroundStyle(Theme.Palette.inkMuted)
                    .fixedSize(horizontal: false, vertical: true)
                if account.isAvailable && !account.state.isSignedIn {
                    Text("You can still sign in here to read, answer and share the reports from scans you made on another iPhone.")
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Palette.inkMuted)
                        .fixedSize(horizontal: false, vertical: true)
                    PrimaryButton(title: "Sign in to see your reports", systemImage: "person.crop.circle") {
                        account.isSheetPresented = true
                    }
                }
            }
        }
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
