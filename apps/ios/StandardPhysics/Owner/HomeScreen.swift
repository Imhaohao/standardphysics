import SwiftUI

/// Home after the first walk: every shop on the account in one list, newest
/// first, each tagged with its next step, then scans still only on this phone.
///
/// Shops come from the account, so a second phone signed in to it finds them
/// too. A scan saved here and never uploaded is listed until it is.
struct HomeScreen: View {
    @ObservedObject var model: AppModel
    @State private var shopToDelete: Journey?

    /// Scans on this phone the account doesn't list yet: never uploaded, or
    /// uploaded to a shop the server hasn't answered about.
    private var phoneOnlyScans: [CapturedScan] {
        let known = Set(model.journeys.map(\.scanID))
        return model.savedScans.filter { scan in
            guard let remote = ResumableUploadStore(captureDirectory: scan.directory).scanID else { return true }
            return !known.contains(remote)
        }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                DraftingPaper()
                List {
                    header
                    if !model.journeys.isEmpty {
                        ShopsSection(
                            journeys: model.journeys,
                            open: model.open,
                            rename: { model.shopToRename = $0 },
                            delete: { shopToDelete = $0 }
                        )
                    }
                    if !phoneOnlyScans.isEmpty {
                        SavedScansSection(
                            scans: phoneOnlyScans,
                            select: { model.screen = .review($0) },
                            delete: { scan in Task { await model.deleteScan(scan) } }
                        )
                    }
                    if let message = model.deletionMessage {
                        Text(message)
                            .font(AppTheme.Typography.secondary)
                            .foregroundStyle(AppTheme.mutedInk)
                            .plainRow(top: AppTheme.Spacing.compact)
                    }
                    recovery
                    walkAnotherShop
                    AccountRow(model: model, session: model.session)
                        .plainRow(top: AppTheme.Spacing.section)
                    Button("How the walk works") { model.screen = .howItWorks }
                        .buttonStyle(AppButtonStyle(.link))
                        .plainRow(top: AppTheme.Spacing.small)
                }
                .listStyle(.plain)
                .scrollContentBackground(.hidden)
                .environment(\.defaultMinListRowHeight, 0)
                .contentMargins(.horizontal, AppTheme.Spacing.page, for: .scrollContent)
                .contentMargins(.bottom, AppTheme.Spacing.page, for: .scrollContent)
                .refreshable { await model.refreshJourneys() }
            }
            .toolbar(.hidden, for: .navigationBar)
            .confirmationDialog(
                "Delete this shop?",
                isPresented: .init(get: { shopToDelete != nil }, set: { if !$0 { shopToDelete = nil } }),
                titleVisibility: .visible,
                presenting: shopToDelete
            ) { journey in
                Button("Delete \(journey.shopName)", role: .destructive) {
                    Task { await model.deleteShop(journey) }
                }
                Button("Keep it", role: .cancel) {}
            } message: { _ in
                Text("The room, the walkthrough and the findings all go with it.")
            }
            .sheet(item: $model.shopToRename) { journey in
                RenameShopSheet(journey: journey) { name in
                    try await model.renameShop(journey.scanID, to: name)
                }
            }
            .task { await model.refreshSavedScanStates() }
            .task { await model.refreshJourneys() }
        }
    }

    @ViewBuilder private var header: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.card) {
            Text(title)
                .font(AppTheme.Typography.hero)
                .foregroundStyle(AppTheme.ink)
                .lineLimit(2)
                .minimumScaleFactor(0.7)
                .accessibilityAddTraits(.isHeader)
            if model.journeys.isEmpty && !model.journeysLoaded {
                ProgressView()
                    .tint(AppTheme.accent)
                    .frame(maxWidth: .infinity, minHeight: 96)
            }
            GuestDeletionNotice(model: model, session: model.session)
        }
        .padding(.bottom, AppTheme.Spacing.small)
        .plainRow(top: 56)
    }

    /// Names the list under it, or the shop-to-be before the first walk has one.
    private var title: String {
        switch model.journeys.count {
        case 0: model.defaultShopName
        case 1: "Your shop"
        default: "Your shops"
        }
    }

    private var hasNothingYet: Bool { model.journeys.isEmpty && phoneOnlyScans.isEmpty }

    @ViewBuilder private var walkAnotherShop: some View {
        if model.canScan {
            Button(hasNothingYet ? "Walk your shop" : "Walk another shop") {
                model.startWalk()
            }
            .buttonStyle(AppButtonStyle(hasNothingYet ? .primary : .secondary))
            .plainRow(top: AppTheme.Spacing.section)
        }
    }

    @ViewBuilder private var recovery: some View {
        ForEach(model.recoveryDirectories, id: \.self) { directory in
            Button("Recover saved room") {
                Task { await model.recoverSavedRoom(directory) }
            }
            .buttonStyle(AppButtonStyle(.secondary))
            .plainRow(top: AppTheme.Spacing.small)
        }
        if let message = model.recoveryMessage {
            Text(message)
                .font(AppTheme.Typography.secondary)
                .foregroundStyle(AppTheme.mutedInk)
                .plainRow(top: AppTheme.Spacing.compact)
        }
    }
}

/// A mark per kind of next step, so a shop's tag says what kind of thing it is
/// before its words are read.
enum NextStepMark {
    private static let symbols: [String: String] = [
        "answers": "questionmark.bubble",
        "photos": "camera",
        "measuring": "ruler",
        "counter": "hand.tap",
        "path": "figure.walk",
        "follow_ups": "ruler",
        "results": "list.bullet.clipboard",
        "checklist": "checklist",
        "done": "checkmark.seal",
        "upload": "arrow.up.circle",
        "failed": "arrow.clockwise",
    ]

    private static let colours: [String: Color] = ["failed": AppTheme.problem, "done": AppTheme.pass]

    static func symbol(for kind: String) -> String {
        symbols[kind] ?? "arrow.right.circle"
    }

    static func colour(for kind: String) -> Color {
        colours[kind] ?? AppTheme.accent
    }
}

/// A shop's next step, small under its name: the step's mark in its colour and
/// the step's words, on a light wash of that colour.
struct NextStepTag: View {
    let step: Journey.NextStep

    private static let wash = 0.12

    var body: some View {
        let colour = NextStepMark.colour(for: step.kind)
        HStack(spacing: AppTheme.Spacing.label) {
            Image(systemName: NextStepMark.symbol(for: step.kind))
                .foregroundStyle(colour)
                .imageScale(.small)
                .accessibilityHidden(true)
            Text(step.title)
                .foregroundStyle(AppTheme.ink)
                .multilineTextAlignment(.leading)
                .lineLimit(2)
        }
        .font(AppTheme.Typography.secondary)
        .padding(.horizontal, AppTheme.Spacing.label)
        .padding(.vertical, AppTheme.Spacing.tag)
        .background(colour.opacity(Self.wash), in: RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
    }
}

/// Renaming a shop, the same in its swipe and its long-press menu.
private struct RenameShopButton: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label("Rename shop", systemImage: "pencil")
        }
    }
}

/// The destructive action on a shop, the same in its swipe and its long-press menu.
private struct DeleteShopButton: View {
    let action: () -> Void

    var body: some View {
        Button(role: .destructive, action: action) {
            Label("Delete this shop", systemImage: "trash")
        }
    }
}

/// Every shop on the account, newest first, each opening at its next step.
private struct ShopsSection: View {
    let journeys: [Journey]
    let open: (Journey) -> Void
    let rename: (Journey) -> Void
    let delete: (Journey) -> Void

    var body: some View {
        Section {
            ForEach(journeys) { journey in
                Button { open(journey) } label: {
                    HStack(spacing: AppTheme.Spacing.compact) {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.label) {
                            Text(journey.shopName)
                                .font(AppTheme.Typography.heading)
                                .foregroundStyle(AppTheme.ink)
                            NextStepTag(step: journey.nextStep)
                        }
                        Spacer(minLength: AppTheme.Spacing.small)
                        Image(systemName: "chevron.right")
                            .foregroundStyle(AppTheme.faintInk)
                            .accessibilityHidden(true)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .contextMenu {
                    RenameShopButton { rename(journey) }
                    DeleteShopButton { delete(journey) }
                }
                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                    DeleteShopButton { delete(journey) }
                        .labelStyle(.iconOnly)
                    RenameShopButton { rename(journey) }
                        .labelStyle(.iconOnly)
                        .tint(AppTheme.accent)
                }
                .listRowBackground(AppTheme.panel)
                .listRowSeparatorTint(AppTheme.rule)
                .listRowInsets(EdgeInsets(
                    top: AppTheme.Spacing.compact, leading: AppTheme.Spacing.card,
                    bottom: AppTheme.Spacing.compact, trailing: AppTheme.Spacing.card
                ))
            }
        }
    }
}

/// A new name for a shop, asked for from its long-press menu or its swipe.
/// When the name doesn't save, the sheet stays open with it still typed.
struct RenameShopSheet: View {
    let journey: Journey
    let rename: (String) async throws -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var name: String
    @State private var saving = false
    @State private var problem: String?

    init(journey: Journey, rename: @escaping (String) async throws -> Void) {
        self.journey = journey
        self.rename = rename
        _name = State(initialValue: journey.shopName)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                DraftingPaper()
                VStack(alignment: .leading, spacing: AppTheme.Spacing.section) {
                    ShopNameField(name: $name, placeholder: journey.shopName, focusOnAppear: true, submit: save)
                    if let problem { FlowProblem(message: problem) }
                    Button(saving ? "Saving" : "Save name", action: save)
                        .buttonStyle(AppButtonStyle())
                        .disabled(saving)
                    Spacer()
                }
                .padding(AppTheme.Spacing.page)
            }
            .navigationTitle("Rename shop")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    /// An unchanged name closes the sheet without asking the server.
    private func save() {
        let chosen = ShopName.chosen(name, fallback: journey.shopName)
        guard !saving else { return }
        guard chosen != journey.shopName else {
            dismiss()
            return
        }
        saving = true
        problem = nil
        Task {
            do {
                try await rename(chosen)
                dismiss()
            } catch {
                problem = ShopName.notSaved
                AccessibilityNotification.Announcement(ShopName.notSaved).post()
            }
            saving = false
        }
    }
}

/// A guest's shops are deleted 30 days after one was last opened. Three
/// days before that, home says when, with the way to keep them beside it.
private struct GuestDeletionNotice: View {
    @ObservedObject var model: AppModel
    @ObservedObject var session: SessionStore

    private var deletionDate: Date? {
        guard let owner = session.owner, owner.guest, let text = owner.deletesAt else { return nil }
        return GuestDeletion.date(from: text)
    }

    var body: some View {
        if let deletionDate, deletionDate.timeIntervalSinceNow < GuestDeletion.warningLead {
            Label(
                "Save your shop by \(deletionDate.formatted(.dateTime.month(.wide).day())) to keep it.",
                systemImage: "clock.badge.exclamationmark"
            )
            .font(AppTheme.Typography.heading)
            .foregroundStyle(AppTheme.ink)
            .padding(AppTheme.Spacing.control)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.coverageMissing.opacity(0.16))
        }
    }
}

enum GuestDeletion {
    static let warningLead: TimeInterval = 3 * 24 * 60 * 60

    static func date(from text: String) -> Date? {
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return withFraction.date(from: text) ?? ISO8601DateFormatter().date(from: text)
    }
}

/// A guest's account row: one way to keep the shop, and sign-in for owners
/// who already have an account.
struct GuestAccountRow: View {
    @ObservedObject var model: AppModel
    @ObservedObject var session: SessionStore
    @State private var saving = false

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.small) {
            if session.owner != nil {
                Button("Save your shop") { saving = true }
                    .buttonStyle(AppButtonStyle(.secondary))
            }
            Button("Sign in to your account") { model.screen = .signIn }
                .buttonStyle(AppButtonStyle(session.owner == nil ? .secondary : .link))
        }
        .sheet(isPresented: $saving) {
            NavigationStack {
                ZStack {
                    DraftingPaper()
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.section) {
                        FlowTitle("Keep your shop on any phone and on the web.")
                        SaveShopOptions(session: session) {
                            saving = false
                            Task { await model.refreshJourneys() }
                        }
                        Spacer()
                    }
                    .padding(AppTheme.Spacing.page)
                }
                .navigationTitle("Save your shop")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("Cancel") { saving = false }
                    }
                }
            }
            .presentationDetents([.medium, .large])
        }
    }
}
