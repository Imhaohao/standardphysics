import SwiftUI

/// One step of the owner's first run: a drawing and a few words that scroll,
/// with the step's actions held at the bottom where a thumb reaches them.
struct FlowPage<Content: View, Actions: View>: View {
    var back: (() -> Void)?
    var exit: FlowExit?
    @ViewBuilder let content: Content
    @ViewBuilder let actions: Actions

    private var showsBar: Bool { back != nil || exit != nil }

    var body: some View {
        NavigationStack {
            ZStack {
                DraftingPaper()
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.section) {
                        content
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, AppTheme.Spacing.page)
                    .padding(.top, showsBar ? AppTheme.Spacing.small : AppTheme.Spacing.page)
                    .padding(.bottom, AppTheme.Spacing.section * 2)
                }
                .scrollBounceBehavior(.basedOnSize)
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                VStack(spacing: AppTheme.Spacing.small) {
                    actions
                }
                .padding(.horizontal, AppTheme.Spacing.page)
                .padding(.top, AppTheme.Spacing.compact)
                .padding(.bottom, AppTheme.Spacing.small)
                .background(alignment: .top) { ActionShelf() }
            }
            .toolbar {
                if let back {
                    ToolbarItem(placement: .topBarLeading) {
                        Button(action: back) {
                            Label("Back", systemImage: "chevron.left")
                                .labelStyle(.titleAndIcon)
                        }
                    }
                }
                if let exit {
                    ToolbarItem(placement: .topBarLeading) {
                        Button(exit.title, role: exit.role, action: exit.action)
                            .foregroundStyle(exit.role == .destructive ? AppTheme.problem : AppTheme.accent)
                    }
                }
            }
            .toolbar(showsBar ? .visible : .hidden, for: .navigationBar)
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

/// A way out of a flow that isn't a step back, like deleting the walk its
/// questions are about.
struct FlowExit {
    let title: String
    var role: ButtonRole?
    let action: () -> Void
}

/// What the actions sit on: the sheet's own colour, fading in over the last
/// few lines of anything scrolled under it rather than cutting it off.
private struct ActionShelf: View {
    var body: some View {
        VStack(spacing: 0) {
            LinearGradient(colors: [AppTheme.canvas.opacity(0), AppTheme.canvas.opacity(0.96)],
                startPoint: .top, endPoint: .bottom)
                .frame(height: AppTheme.Spacing.section)
            AppTheme.canvas.opacity(0.96)
        }
        .padding(.top, -AppTheme.Spacing.section)
        .ignoresSafeArea(edges: .bottom)
        .allowsHitTesting(false)
    }
}

/// The heading of a first-run step.
struct FlowTitle: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(AppTheme.Typography.title)
            .foregroundStyle(AppTheme.ink)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityAddTraits(.isHeader)
    }
}

/// The line under a step's heading, for a fact the heading can't carry.
struct FlowDetail: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(AppTheme.Typography.body)
            .foregroundStyle(AppTheme.mutedInk)
            .fixedSize(horizontal: false, vertical: true)
    }
}

/// How far through the in-shop questions and photos the owner is, as one
/// short bar per request.
struct StepProgress: View {
    let done: Int
    let total: Int

    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<max(total, 1), id: \.self) { index in
                Rectangle()
                    .fill(index < done ? AppTheme.accent : AppTheme.rule)
                    .frame(height: 4)
            }
        }
        .animation(AppTheme.Motion.quick, value: done)
        .accessibilityElement()
        .accessibilityLabel("\(min(done + 1, total)) of \(total)")
    }
}

/// The one field a shop's name is typed in: before a walk, on review, and
/// when renaming a shop from home. Left empty, the shop is called
/// `placeholder`, which the field shows in grey.
struct ShopNameField: View {
    @Binding var name: String
    let placeholder: String
    var focusOnAppear = false
    var submit: () -> Void = {}
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.label) {
            Text("Shop name")
                .font(AppTheme.Typography.secondary)
                .foregroundStyle(AppTheme.mutedInk)
                .accessibilityHidden(true)
            TextField("Shop name", text: $name, prompt: Text(placeholder))
                .textInputAutocapitalization(.words)
                .submitLabel(.done)
                .focused($focused)
                .onSubmit(submit)
                .onChange(of: name) { _, typed in
                    let limited = ShopName.limited(typed)
                    if limited != typed { name = limited }
                }
                .fieldSurface(focused: focused)
        }
        .onAppear { focused = focusOnAppear }
    }
}

/// A problem that stopped a step, said as what to do next.
struct FlowProblem: View {
    let message: String

    var body: some View {
        Label(message, systemImage: "exclamationmark.circle")
            .font(AppTheme.Typography.secondary)
            .foregroundStyle(AppTheme.problem)
            .fixedSize(horizontal: false, vertical: true)
    }
}
