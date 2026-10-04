import SwiftUI

/// Screens 5 to 8: one request per screen while the walk uploads, then the
/// measuring wait.
struct ShopSetupScreen: View {
    @ObservedObject var app: AppModel
    @ObservedObject var setup: ShopSetupModel
    @State private var confirmingDelete = false
    @State private var deleting = false

    /// Lets the owner drop the walk without answering the rest of its questions.
    private var deleteScan: FlowExit {
        FlowExit(title: deleting ? "Deleting" : "Delete scan", role: .destructive) { confirmingDelete = true }
    }

    var body: some View {
        Group {
            switch setup.step {
            case .preparing:
                PreparingView()
            case .question(let request):
                QuickAnswerView(setup: setup, request: request, exit: deleteScan)
                    .id(request.id)
            case .photo(let request):
                QuickPhotoView(setup: setup, request: request, exit: deleteScan)
                    .id(request.id)
            case .pushForce(let request):
                DoorPushView(setup: setup, request: request, exit: deleteScan)
                    .id(request.id)
            case .measuring:
                MeasuringView(app: app, setup: setup)
            }
        }
        .disabled(deleting)
        .transition(.opacity)
        .animation(AppTheme.Motion.quick, value: setup.step)
        .confirmationDialog("Delete this scan?", isPresented: $confirmingDelete, titleVisibility: .visible) {
            Button("Delete scan", role: .destructive) {
                deleting = true
                Task { await app.deleteWalk(setup) }
            }
            Button("Keep it", role: .cancel) {}
        } message: {
            Text("The room, the walkthrough and your answers so far all go with it.")
        }
        .task { await setup.begin() }
    }
}

private struct PreparingView: View {
    var body: some View {
        ZStack {
            DraftingPaper()
            ProgressView()
                .controlSize(.large)
                .tint(AppTheme.accent)
        }
    }
}

/// Screen 5: a yes or no the scan can't see, like whether customers use a
/// restroom.
private struct QuickAnswerView: View {
    @ObservedObject var setup: ShopSetupModel
    let request: OwnerRequest
    let exit: FlowExit

    var body: some View {
        FlowPage(exit: exit) {
            StepProgress(done: setup.progress.done, total: setup.progress.total)
            SketchSheet(height: 200) { QuestionSketch(requestID: request.id) }
            FlowTitle(request.title)
            FlowDetail(request.detail)
            if let problem = setup.problem { FlowProblem(message: problem) }
        } actions: {
            StepActions(outbox: setup.outbox) {
                HStack(spacing: AppTheme.Spacing.small) {
                    Button("Yes") { setup.answer(true) }
                        .buttonStyle(AppButtonStyle())
                    Button("No") { setup.answer(false) }
                        .buttonStyle(AppButtonStyle())
                }
                .disabled(setup.isSending)
            }
        }
    }
}

/// Screen 6: one photo, with a drawing of the shot to take and the line the
/// server writes about what it will be checked for. The step moves on once
/// the camera has closed, and the photo sends while the owner carries on.
private struct QuickPhotoView: View {
    @ObservedObject var setup: ShopSetupModel
    let request: OwnerRequest
    let exit: FlowExit
    @State private var takingPhoto = false
    @State private var takenPhoto: Data?

    var body: some View {
        FlowPage(exit: exit) {
            StepProgress(done: setup.progress.done, total: setup.progress.total)
            SketchSheet(height: 230) { SamplePhoto(requestID: request.id) }
            FlowTitle(request.title)
            FlowDetail(request.detail)
            if let problem = setup.problem { FlowProblem(message: problem) }
        } actions: {
            StepActions(outbox: setup.outbox) {
                Button("Take photo") { takingPhoto = true }
                    .buttonStyle(AppButtonStyle())
                Button("Skip for now") { setup.skip() }
                    .buttonStyle(AppButtonStyle(.link))
            }
        }
        .disabled(setup.isSending)
        .fullScreenCover(isPresented: $takingPhoto, onDismiss: sendTakenPhoto) {
            PhotoCapture { image in
                takenPhoto = image.flatMap(PhotoEncoding.jpeg(from:))
                takingPhoto = false
            }
            .ignoresSafeArea()
        }
    }

    private func sendTakenPhoto() {
        guard let jpeg = takenPhoto else { return }
        takenPhoto = nil
        setup.sendPhoto(jpeg)
    }
}

/// Screen 7: how hard the inside doors are to push, in pounds, asked only
/// when customers go through one.
private struct DoorPushView: View {
    @ObservedObject var setup: ShopSetupModel
    let request: OwnerRequest
    let exit: FlowExit
    @State private var pounds = ""
    @FocusState private var fieldFocused: Bool

    private var reading: Double? {
        Double(pounds.replacingOccurrences(of: ",", with: ".")).flatMap { $0 > 0 && $0 < 10_000 ? $0 : nil }
    }

    var body: some View {
        FlowPage(exit: exit) {
            StepProgress(done: setup.progress.done, total: setup.progress.total)
            SketchSheet(height: 220) { PushGaugeSketch() }
            FlowTitle(request.title)
            FlowDetail(request.detail)
            HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.small) {
                TextField("", text: $pounds)
                    .keyboardType(.decimalPad)
                    .font(AppTheme.Typography.title)
                    .monospacedDigit()
                    .focused($fieldFocused)
                    .accessibilityLabel("Push force in pounds")
                Text("lb")
                    .font(AppTheme.Typography.title)
                    .foregroundStyle(AppTheme.mutedInk)
                    .accessibilityHidden(true)
            }
            .fieldSurface(focused: fieldFocused)
            .onAppear { fieldFocused = true }
            if let problem = setup.problem { FlowProblem(message: problem) }
        } actions: {
            StepActions(outbox: setup.outbox) {
                Button(setup.isSending ? "Saving" : "Save") {
                    if let reading { setup.savePushForce(reading) }
                }
                .buttonStyle(AppButtonStyle())
                .disabled(reading == nil)
                Button("Skip for now") { setup.skip() }
                    .buttonStyle(AppButtonStyle(.link))
            }
        }
        .disabled(setup.isSending)
    }
}

/// A step's actions, under a quiet line saying how many photos are still
/// sending. The line goes once the last one has arrived.
struct StepActions<Actions: View>: View {
    @ObservedObject var outbox: PhotoOutbox
    @ViewBuilder let actions: Actions

    var body: some View {
        VStack(spacing: AppTheme.Spacing.small) {
            if outbox.count > 0 {
                photosSending
                    .transition(.opacity)
            }
            actions
        }
        .animation(AppTheme.Motion.quick, value: outbox.count > 0)
    }

    private var photosSending: some View {
        Label {
            Text("Sending ^[\(outbox.count) photo](inflect: true)")
        } icon: {
            ProgressView()
                .controlSize(.small)
                .tint(AppTheme.mutedInk)
                .accessibilityHidden(true)
        }
        .font(AppTheme.Typography.secondary)
        .foregroundStyle(AppTheme.mutedInk)
        .accessibilityElement(children: .combine)
    }
}
