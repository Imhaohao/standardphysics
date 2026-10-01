#if DEBUG
import Foundation
import simd

/// Opens one screen with made-up data, so every screen and state can be
/// looked at in the simulator without a server, a LiDAR phone or a walk.
///
///     SIMCTL_CHILD_SP_DEBUG_SCREEN=photo:door_hardware xcrun simctl launch booted com.standardphysics.capture
///
/// On the shop setup screens, `SP_DEBUG_PHOTOS=sending` opens with the photos
/// taken before the screen still on their way, and `SP_DEBUG_PHOTOS=failing`
/// opens with them sending to a server that refuses every try, so they come
/// back to be taken again.
///
/// Debug builds only. The request wording is the server's, copied from
/// services/api/standardphysics_api/owner_requests.py and
/// packages/agents/standardphysics_agents/copy.py.
@MainActor
enum DebugLaunch {
    static func apply(to model: AppModel) -> Bool {
        if let token = ProcessInfo.processInfo.environment["SP_DEBUG_TOKEN"] {
            model.session.adoptForDebugging(token: token)
        }
        guard let value = ProcessInfo.processInfo.environment["SP_DEBUG_SCREEN"] else { return false }
        let parts = value.split(separator: ":", maxSplits: 1).map(String.init)
        guard let screen = screen(parts[0], argument: parts.count > 1 ? parts[1] : nil, model: model) else { return false }
        model.screen = screen
        return true
    }

    private static func screen(_ name: String, argument: String?, model: AppModel) -> AppModel.Screen? {
        if let simple = simpleScreens[name] { return simple }
        switch name {
        case "home":
            model.showForDebugging(journeys: journeys(argument))
            return .home
        case "question", "photo", "push", "measuring":
            return .setup(setup(name, argument: argument, model: model))
        case "walk":
            return .walkPreview(walk(argument ?? "progress"))
        case "setup":
            return argument.flatMap(UUID.init(uuidString:)).map { .setup(ShopSetupModel(scanID: $0, app: model)) }
        case "shop":
            return argument.flatMap(UUID.init(uuidString:)).map { .web(.owner($0)) }
        case "live":
            Task { await model.refreshJourneys() }
            return .home
        default:
            return nil
        }
    }

    private static let simpleScreens: [String: AppModel.Screen] = [
        "welcome": .welcome,
        "beforeYouWalk": .beforeYouWalk,
        "camera": .cameraAccess,
        "howItWorks": .howItWorks,
        "unsupported": .unsupported,
        "signIn": .signIn,
        "example": .web(.example),
        "capture": .capture,
    ]

    // MARK: Requests

    static let requests: [String: OwnerRequest] = [
        "restroom": ask("restroom", "yes_no", "Do customers use a restroom?", "Count it if customers can ask to use it."),
        "inside_doors": ask(
            "inside_doors", "yes_no", "Do customers go through any doors inside the shop, like a restroom door?",
            "Doors between rooms count. The front door doesn\u{2019}t."),
        "entrance_threshold": ask(
            "entrance_threshold", "photo", "Send a low photo of the front doorway",
            "Open the door, crouch just outside and hold your phone a few inches off the ground, pointed into the shop. If you have a tape measure, stand it next to the threshold so we can read its height against the half inch the standard allows."),
        "door_hardware": ask(
            "door_hardware", "photo", "Send a photo of the front door handle",
            "Straight on, close enough to see its shape. We\u{2019}ll check it opens with a closed fist and sits between 34 and 48 inches up."),
        "floor_surface": ask(
            "floor_surface", "photo", "Send a photo of the floor just inside the front door",
            "Include any mat. We\u{2019}ll check it lies flat, stays put, and that carpet is no thicker than half an inch."),
        "restroom_turning_space": ask(
            "restroom_turning_space", "photo", "Send a photo of the customer restroom from the doorway",
            "Stand in the door and get the whole room in. We\u{2019}ll check there\u{2019}s a 60 inch circle to turn around in."),
        "door_opening_force": ask(
            "door_opening_force", "number", "How hard are the inside doors to push open?",
            "A door pressure gauge from a hardware store measures it. Push each inside door open with it and send the highest number.",
            unit: "lb"),
    ]

    private static func ask(_ id: String, _ kind: String, _ title: String, _ detail: String, unit: String? = nil) -> OwnerRequest {
        OwnerRequest(id: id, kind: kind, timing: "in_shop", title: title, detail: detail, unit: unit, status: "open")
    }

    /// The in-shop requests, in the order the server asks them.
    private static let order = ["restroom", "inside_doors", "entrance_threshold", "door_hardware", "floor_surface",
                                "restroom_turning_space", "door_opening_force"]

    /// The flow from the named screen on, with every request before it answered.
    private static func setup(_ name: String, argument: String?, model: AppModel) -> ShopSetupModel {
        let opensAt = firstOpen(name, argument: argument).flatMap { order.firstIndex(of: $0) } ?? order.count
        let answered = Array(order.prefix(opensAt))
        let photoServer = ProcessInfo.processInfo.environment["SP_DEBUG_PHOTOS"]
        let setup = ShopSetupModel(
            debugRequests: order.compactMap { requests[$0] },
            answered: Set(answered),
            sending: photoServer == nil ? [] : answered.filter { requests[$0]?.isPhoto == true },
            outbox: outbox(photoServer),
            app: model)
        setup.debugPrompt = name == "measuring" ? measuringPrompt(argument) : nil
        return setup
    }

    /// The request a screen opens on. The measuring wait has none left.
    private static func firstOpen(_ name: String, argument: String?) -> String? {
        switch name {
        case "push": "door_opening_force"
        case "measuring": nil
        case "photo": argument ?? "door_hardware"
        default: argument ?? "restroom"
        }
    }

    /// Photos on a debug screen never reach a server. A photo taken there
    /// arrives after four seconds, unless `SP_DEBUG_PHOTOS` names a server
    /// that holds every photo or refuses it.
    private static func outbox(_ photoServer: String?) -> PhotoOutbox {
        switch photoServer {
        case "sending": PhotoOutbox { _ in try await Task.sleep(for: .seconds(3_600)) }
        case "failing": PhotoOutbox { _ in throw OwnerAPIError.unreachable }
        default: PhotoOutbox { _ in try await Task.sleep(for: .seconds(4)) }
        }
    }

    private static func measuringPrompt(_ argument: String?) -> MeasuringView.Prompt {
        switch argument {
        case "notifications": .notifications
        case "waiting": .none
        default: .save
        }
    }

    // MARK: Home

    private static func journeys(_ argument: String?) -> [Journey] {
        let shops: [(String, String, String, Int?)] = switch argument {
        case "photos": [("Tea House", "photos", "Take 2 more photos", 2)]
        case "measuring": [("Tea House", "measuring", "We\u{2019}re measuring your shop", nil)]
        case "many": [
            ("Tea House", "checklist", "1 of 3 done. Next: move the display case 6 inches toward the wall", 2),
            ("Tea House Annex", "results", "Your results are ready. 2 things to fix", 2),
            ("Corner Books", "photos", "Take 1 more photo", 1),
        ]
        default: [("Tea House", "results", "Your results are ready. 3 things to fix", 3)]
        }
        return shops.map { name, kind, title, count in
            Journey(scanID: UUID(), shopName: name, stage: "results",
                nextStep: .init(kind: kind, title: title, count: count), toolsUnlocked: kind != "photos")
        }
    }

    // MARK: The walk

    /// A 6 by 4 metre room with its four walls, some of them done.
    private static func walk(_ state: String) -> CaptureSessionStore {
        let walls: [(SIMD3<Float>, Float, Float)] = [
            (SIMD3(0, 1.4, -2), 0, 6), (SIMD3(3, 1.4, 0), -.pi / 2, 4),
            (SIMD3(0, 1.4, 2), .pi, 6), (SIMD3(-3, 1.4, 0), .pi / 2, 4),
        ]
        let surfaces = walls.map { centre, angle, width in
            var transform = simd_float4x4(simd_quatf(angle: angle, axis: SIMD3(0, 1, 0)))
            transform.columns.3 = SIMD4(centre, 1)
            return SurfaceSnapshot(id: UUID(), width: width, height: 2.8, transform: transform, confidence: .high)
        }
        let finished = finishedWalls(for: state)
        let coverage = zip(surfaces.indices, surfaces).map { index, surface in
            let segments = (0..<10).map { index < finished || (index == finished && $0 < 4) }
            let fraction = Double(segments.filter { $0 }.count) / 10
            return SurfaceCoverage(id: surface.id, observedFraction: fraction, observedSegments: segments,
                viewpointCount: index < finished ? 3 : 1, highConfidence: true, area: surface.width * 2.8)
        }
        var snapshot = CoverageSnapshot(surfaces: coverage)
        let started = state == "start"
        snapshot.unfinishedDirection = CoverageAngle(radians: started ? 0 : .pi)
        snapshot.instruction = started ? CoverageSnapshot.openingInstruction : "Point the phone at the wall behind you."
        let store = CaptureSessionStore()
        store.showForDebugging(coverage: snapshot, surfaces: surfaces, secondsLeft: state == "warning" ? 24 : nil)
        return store
    }

    private static func finishedWalls(for state: String) -> Int {
        switch state {
        case "start": 0
        case "complete": 4
        default: 2
        }
    }
}
#endif
