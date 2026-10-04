import Foundation

/// The owner's first minutes after a walk: the quick answers, the quick
/// photos and the door push, then the measuring wait.
///
/// The server keeps the requests and says which are still open, so each
/// answer is followed by a fresh list. A "no" to the restroom closes the
/// restroom photo on the server, and the next list simply leaves it out.
/// A photo changes nothing about what comes next, so the owner moves on as
/// soon as it's taken and the photo sends while they carry on.
@MainActor
final class ShopSetupModel: ObservableObject, Identifiable {
    enum Step: Equatable {
        case preparing
        case question(OwnerRequest)
        case photo(OwnerRequest)
        case pushForce(OwnerRequest)
        case measuring
    }

    static let unsentPhotoProblem = "That photo didn\u{2019}t send. Take it again."

    let id = UUID()
    /// This phone's upload of the walk, when the walk was taken on it.
    let upload: UploadViewModel?
    let outbox: PhotoOutbox
    @Published private(set) var scanID: UUID?
    @Published private(set) var step: Step = .preparing
    @Published private(set) var isSending = false
    @Published private(set) var problem: String?
    /// Set once the shop has a model, which is when the web takes over: it
    /// asks where customers pay and which path they take, then shows results.
    @Published private(set) var handover: Journey.NextStep?
    var isMeasured: Bool { handover != nil }
    @Published private(set) var progress = (done: 0, total: 0)

    private weak var app: AppModel?
    private var requests: [OwnerRequest] = []
    /// Answered, skipped or photographed on this phone, so a slow or failed
    /// refresh never asks the same thing twice. A photo counts as soon as it's
    /// taken, so it isn't asked for again while it's still sending.
    private var settled: Set<String> = []
    /// What to tell the owner about each photo that never reached the server,
    /// shown when its step comes round again.
    private var unsentPhotos: [String: String] = [:]

    init(upload: UploadViewModel, app: AppModel) {
        self.upload = upload
        self.app = app
        scanID = upload.scanID
        outbox = PhotoOutbox(upload: Self.photoUpload(through: app))
    }

    init(scanID: UUID, app: AppModel) {
        upload = nil
        self.app = app
        self.scanID = scanID
        outbox = PhotoOutbox(upload: Self.photoUpload(through: app))
    }

    /// A flow over requests already in hand, which sends its photos through
    /// `outbox`. The debug screens and the tests start here, with no server.
    init(scanID: UUID, requests: [OwnerRequest], answered: Set<String> = [], outbox: PhotoOutbox,
         app: AppModel? = nil) {
        upload = nil
        self.app = app
        self.scanID = scanID
        self.outbox = outbox
        self.requests = requests
        settled = answered
        advance()
    }

    /// Asks for the session each time, so a photo still trying after the
    /// owner signs in goes with the new one.
    private static func photoUpload(through app: AppModel) -> PhotoOutbox.Upload {
        { [weak app] photo in
            guard let api = app?.api() else { throw OwnerAPIError.signedOut }
            try await api.sendPhoto(scanID: photo.scanID, requestID: photo.requestID, jpeg: photo.jpeg)
        }
    }

    /// Waits for the upload to give the walk a scan on the server, then asks
    /// for its requests. A walk that could not start uploading goes straight
    /// to the wait, which says what went wrong.
    func begin() async {
#if DEBUG
        if isDebugPreview { return }
#endif
        while scanID == nil {
            if let found = upload?.scanID {
                scanID = found
                break
            }
            if upload?.errorMessage != nil || upload == nil {
                step = .measuring
                return
            }
            do { try await Task.sleep(for: .milliseconds(300)) } catch { return }
        }
        await refresh()
    }

    func refresh() async {
        guard let scanID, let api = app?.api() else {
            step = .measuring
            return
        }
        do {
            requests = try await api.requests(scanID: scanID)
            problem = nil
        } catch OwnerAPIError.signedOut {
            problem = OwnerAPIError.signedOut.localizedDescription
        } catch {
            if requests.isEmpty { step = .measuring }
        }
        advance()
    }

    func answer(_ yes: Bool) {
        send { api, scanID, request in
            try await api.answer(scanID: scanID, requestID: request.id, yes: yes)
        }
    }

    func savePushForce(_ pounds: Double) {
        send { api, scanID, request in
            try await api.answer(scanID: scanID, requestID: request.id, number: pounds)
        }
    }

    /// Moves on as soon as the photo is taken, and leaves the photo sending.
    func sendPhoto(_ jpeg: Data) {
        guard case .photo(let request) = step, let scanID else { return }
        settle(request.id)
        problem = nil
        Haptics.sent()
        startSending(PhotoOutbox.Photo(scanID: scanID, requestID: request.id, jpeg: jpeg))
        advance()
    }

    func skip() {
        send { api, scanID, request in
            try await api.skip(scanID: scanID, requestID: request.id)
        }
    }

    /// Watches the shop's journey until it moves past the phone's part.
    /// Without a journey (an older server, or no connection) the walk's own
    /// upload reaching Checking or Ready says the same thing.
    func watchForResults() async {
#if DEBUG
        if isDebugPreview { return }
#endif
        while !Task.isCancelled && handover == nil {
            if await pickUpLateScan() { return }
            handover = await measuredStep()
            if handover != nil { return }
            do { try await Task.sleep(for: .seconds(3)) } catch { return }
        }
    }

    /// A walk whose upload only got going on a retry from the wait screen
    /// still has its questions to ask, so the flow goes back to them.
    private func pickUpLateScan() async -> Bool {
        guard scanID == nil, let found = upload?.scanID else { return false }
        scanID = found
        await refresh()
        return step != .measuring
    }

    private func measuredStep() async -> Journey.NextStep? {
        if let scanID, let journey = try? await app?.api()?.journey(scanID: scanID) {
            return journey.isBeforeResults ? nil : journey.nextStep
        }
        guard let state = upload?.state, state == .checking || state == .ready else { return nil }
        return Journey.NextStep(kind: "results", title: "Open your shop", count: nil)
    }

#if DEBUG
    /// A screen of the flow with made-up requests, for `SP_DEBUG_SCREEN`.
    /// The photos in `sending` were taken before the screen and start out
    /// still on their way.
    convenience init(debugRequests: [OwnerRequest], answered: Set<String>, sending: [String],
                     outbox: PhotoOutbox, app: AppModel) {
        let scanID = UUID()
        self.init(scanID: scanID, requests: debugRequests, answered: answered, outbox: outbox, app: app)
        isDebugPreview = true
        for requestID in sending {
            startSending(PhotoOutbox.Photo(scanID: scanID, requestID: requestID, jpeg: Data()))
        }
    }

    private(set) var isDebugPreview = false
    var debugPrompt: MeasuringView.Prompt?
#endif

    private var currentRequest: OwnerRequest? {
        switch step {
        case .question(let request), .photo(let request), .pushForce(let request): request
        case .preparing, .measuring: nil
        }
    }

    private func send(_ action: @escaping (OwnerAPI, UUID, OwnerRequest) async throws -> Void) {
        guard !isSending, let request = currentRequest, let scanID, let api = app?.api() else { return }
        isSending = true
        problem = nil
        Task {
            do {
                try await action(api, scanID, request)
                settle(request.id)
                Haptics.sent()
                await refresh()
            } catch {
                problem = error.localizedDescription
            }
            isSending = false
        }
    }

    private func settle(_ requestID: String) {
        settled.insert(requestID)
        unsentPhotos[requestID] = nil
    }

    private func startSending(_ photo: PhotoOutbox.Photo) {
        outbox.send(photo) { [weak self] error in
            self?.photoDidNotSend(photo.requestID, because: error)
        }
    }

    /// A photo the server never got is asked for again. While the owner is on
    /// another step, it waits until that step is done so the screen never
    /// changes under them. On the measuring wait it comes back straight away.
    private func photoDidNotSend(_ requestID: String, because error: Error) {
        settled.remove(requestID)
        unsentPhotos[requestID] = Self.problem(sending: error)
        progress = Self.progress(of: requests, settled: settled)
        if step == .measuring { advance() }
    }

    /// Another photo can't fix an ended session, so that one says what can.
    private static func problem(sending error: Error) -> String {
        let sessionEnded = error as? OwnerAPIError == .signedOut
        return sessionEnded ? OwnerAPIError.signedOut.localizedDescription : unsentPhotoProblem
    }

    private func advance() {
        let remaining = requests.filter { !settled.contains($0.id) }
        step = Self.nextStep(in: remaining)
        progress = Self.progress(of: requests, settled: settled)
        if case .photo(let request) = step, let unsent = unsentPhotos[request.id] { problem = unsent }
    }

    /// The questions first, because a "no" removes a photo or a number that
    /// would otherwise be asked for, then the photos, then the door push.
    nonisolated static func nextStep(in requests: [OwnerRequest]) -> Step {
        let open = requests.filter { $0.isInShop && $0.isOpen }
        if let question = open.first(where: \.isYesOrNo) { return .question(question) }
        if let photo = open.first(where: \.isPhoto) { return .photo(photo) }
        if let push = open.first(where: \.isPushForce) { return .pushForce(push) }
        return .measuring
    }

    nonisolated static func progress(of requests: [OwnerRequest], settled: Set<String>) -> (done: Int, total: Int) {
        let asked = requests.filter { $0.isInShop && $0.status != "not_applicable" && $0.kind != "another_look" }
        let open = asked.filter { $0.isOpen && !settled.contains($0.id) }
        return (asked.count - open.count, asked.count)
    }
}

/// Photos taken in the shop that are still on their way to the server.
///
/// Each photo keeps its JPEG until the server has it. A send that fails is
/// tried again after a short wait, then after a longer one, because a phone
/// in a shop can lose its signal for a few seconds at a time. When the third
/// try fails too, the photo is handed back as not sent.
@MainActor
final class PhotoOutbox: ObservableObject {
    struct Photo: Sendable {
        let scanID: UUID
        let requestID: String
        let jpeg: Data
    }

    typealias Upload = @MainActor (Photo) async throws -> Void
    typealias Wait = @MainActor (Duration) async throws -> Void

    /// The waits before the second try and the third.
    nonisolated static let retryWaits: [Duration] = [.seconds(2), .seconds(6)]

    /// How many photos are still on their way.
    @Published private(set) var count = 0

    private let upload: Upload
    private let wait: Wait
    private let retryWaits: [Duration]

    init(retryWaits: [Duration] = PhotoOutbox.retryWaits,
         wait: @escaping Wait = { try await Task.sleep(for: $0) },
         upload: @escaping Upload) {
        self.retryWaits = retryWaits
        self.wait = wait
        self.upload = upload
    }

    /// Starts the photo on its way and returns straight away. `failed` hears
    /// the last try's error when none of the tries got through.
    func send(_ photo: Photo, failed: @escaping @MainActor (Error) -> Void) {
        count += 1
        Task {
            let grace = BackgroundGrace(named: "Sending a photo")
            defer {
                grace.end()
                count -= 1
            }
            do { try await deliver(photo) } catch { failed(error) }
        }
    }

    private func deliver(_ photo: Photo) async throws {
        for retryWait in retryWaits {
            do {
                try await upload(photo)
                return
            } catch {
                try await wait(retryWait)
            }
        }
        try await upload(photo)
    }
}
