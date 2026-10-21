import Foundation

/// Fixture scans and findings for previews, tests and `-screen` launches. Limits match the
/// ADA 2010 Standards and CBC 11B sections they cite.
nonisolated enum SampleData {
    static let salesFloor = "Sales floor"
    static let restroom = "Restroom"

    static let subjects: [String: ReportSubject] = [
        "counter-1": ReportSubject(id: "counter-1", roomName: salesFloor, label: "Sales counter"),
        "door-entry": ReportSubject(id: "door-entry", roomName: salesFloor, label: "Front door"),
        "shelf-1": ReportSubject(id: "shelf-1", roomName: salesFloor, label: "Display shelf"),
        "aisle-1": ReportSubject(id: "aisle-1", roomName: salesFloor, label: "Aisle by the register"),
        "door-restroom": ReportSubject(id: "door-restroom", roomName: restroom, label: "Restroom door"),
        "toilet-1": ReportSubject(id: "toilet-1", roomName: restroom, label: "Toilet"),
        "grab-1": ReportSubject(id: "grab-1", roomName: restroom, label: "Rear grab bar"),
        "mirror-1": ReportSubject(id: "mirror-1", roomName: restroom, label: "Mirror"),
        "sink-1": ReportSubject(id: "sink-1", roomName: restroom, label: "Sink"),
        "object-7": ReportSubject(id: "object-7", roomName: salesFloor, label: "Object by the window"),
    ]

    static let findings: [Finding] = salesFloorFindings + restroomFindings

    static let salesFloorFindings: [Finding] = [
        pair("904.4.1", "counter-1", title: "Sales counter height", inches: 35.5, federal: ("≤ 36 in", .pass), california: ("≤ 34 in", .fail),
             message: "The counter is 35.5 in high. Lower a 36 in long stretch of it to 34 in or less."),
        pair("404.2.4.1", "door-entry", title: "Clear space beside the latch", inches: 12, federal: ("≥ 18 in", .fail), california: ("≥ 18 in", .fail),
             message: "There's 12 in of clear wall beside the latch on the pull side. Clear at least 18 in so someone in a wheelchair can pull the door open."),
        pair("404.2.3", "door-entry", inches: 34, federal: ("≥ 32 in", .pass), california: ("≥ 32 in", .pass),
             message: "The doorway is 34 in clear when the door is open."),
        pair("308.2.1", "shelf-1", inches: 46, federal: ("≤ 48 in", .pass), california: ("≤ 48 in", .pass),
             message: "The top shelf is 46 in high, within forward reach."),
        pair("403.5.1", "aisle-1", inches: 33, federal: ("≥ 36 in", .fail), california: ("≥ 36 in", .fail),
             message: "The aisle narrows to 33 in beside the register. Move the display back to leave 36 in clear."),
    ].flatMap { $0 }

    static let restroomFindings: [Finding] = [
        pair("404.2.3", "door-restroom", title: "Door clear width", inches: 30.5, federal: ("≥ 32 in", .fail), california: ("≥ 32 in", .fail),
             message: "The doorway is 30.5 in clear. Swap in offset hinges or a wider door to reach 32 in."),
        question("703.4.1", "door-restroom", "Is there a sign with raised letters and Braille on the wall beside the door's latch side?",
                 ask: FindingAsk(metric: "sign.braille_present", prompt: "Is there a sign with raised letters and Braille on the wall beside the door's latch side?", valueType: .boolean, photo: true)),
        question("404.2.7", "door-restroom", "Can you open the door with a closed fist, without gripping or twisting the handle?"),
        question("404.2.9", "door-restroom", "How hard is the door to push open?",
                 ask: FindingAsk(metric: "door.opening_force", prompt: "How many pounds of force does it take to push the door open? A door pull gauge reads this directly.", valueType: .number, unit: "lbf")),
        pair("604.2", "toilet-1", inches: 16.5, federal: ("16–18 in", .pass), california: ("17–18 in", .fail),
             message: "The middle of the toilet is 16.5 in from the side wall. Move it so the centre sits 17 to 18 in out."),
        pair("609.4", "grab-1", inches: 34, federal: ("33–36 in", .pass), california: ("33–36 in", .pass),
             message: "The grab bar is 34 in above the floor."),
        pair("603.3", "mirror-1", inches: 41.5, federal: ("≤ 40 in", .fail), california: ("≤ 40 in", .fail),
             message: "The bottom of the mirror is 41.5 in up. Lower it, or tilt it, so the glass starts at 40 in or lower."),
        pair("606.3", "sink-1", inches: 33.5, federal: ("≤ 34 in", .pass), california: ("≤ 34 in", .pass),
             message: "The sink rim is 33.5 in high."),
    ].flatMap { $0 }

    /// Server findings with no code behind them, asking the owner to look at something.
    static let ownerChecks: [Finding] = [
        Finding(
            ruleID: "label.unresolved", jurisdiction: .system, section: "", subjectID: "object-7", status: .needsInfo,
            measured: nil, required: "", message: "This object could not be identified in time, so rules that depend on it need a manual check.",
            title: "Object not identified", severity: .info
        ),
    ]

    static let provisionalFindings: [Finding] = salesFloorFindings

    static func report(for manifest: ScanManifest) -> ScanReport {
        let names = manifest.rooms.map(\.name)
        return ScanReport(
            scanID: manifest.scanID,
            name: manifest.name,
            completedAt: .now,
            roomNames: names.isEmpty ? [salesFloor, restroom] : names,
            subjects: subjects,
            findings: findings
        )
    }

    static let completedReport = ScanReport(
        scanID: UUID(uuidString: "6F1C2A4E-58D3-4C38-9D53-1F0F8E2B7A10")!,
        name: "Hollis Street Bakery",
        completedAt: Date(timeIntervalSinceNow: -26 * 3600),
        roomNames: [salesFloor, restroom],
        subjects: subjects,
        findings: findings + ownerChecks
    )

    static let earlierReport = ScanReport(
        scanID: UUID(uuidString: "0B7E4D21-3A9F-4B6C-8E15-2C4D6F8A9B30")!,
        name: "Juniper Books",
        completedAt: Date(timeIntervalSinceNow: -9 * 86400),
        roomNames: [salesFloor],
        subjects: subjects,
        findings: salesFloorFindings.filter { $0.status == .pass }
    )

    static func unfinishedManifest(roomsSaved: Int = 2) -> ScanManifest {
        let names = [salesFloor, "Back room", restroom]
        return ScanManifest(
            scanID: UUID(uuidString: "A3D9F0C2-7B14-4E6A-9C21-5D8E0F3B6A47")!,
            name: "Marlow Coffee",
            startedAt: Date(timeIntervalSinceNow: -50 * 60),
            phase: .paused(room: roomsSaved + 1, reason: .backgrounded),
            rooms: (0..<roomsSaved).map { index in
                RoomRecord(index: index + 1, name: names[index % names.count], capturedRoomFile: "room-\(index + 1).json", completedAt: Date(timeIntervalSinceNow: Double(-40 + index * 10) * 60))
            },
            worldMapFile: "world.map",
            worldMapSavedAt: Date(timeIntervalSinceNow: -20 * 60),
            relocalizationSnapshotFile: "snapshot.jpg"
        )
    }

    private typealias Requirement = (required: String, status: FindingStatus)

    private static func pair(
        _ section: String, _ subject: String, title: String? = nil, inches: Double,
        federal: Requirement, california: Requirement, message: String
    ) -> [Finding] {
        let measured = MeasuredValue(value: inches, unit: "in")
        return [
            Finding(
                ruleID: "ADA2010-\(section)", jurisdiction: .ada2010, section: section, subjectID: subject, status: federal.status,
                measured: measured, required: federal.required, message: message, title: title, severity: .violation,
                counterpartRuleID: "CBC11B-\(section)"
            ),
            Finding(
                ruleID: "CBC11B-\(section)", jurisdiction: .cbc11b, section: "11B-\(section)", subjectID: subject, status: california.status,
                measured: measured, required: california.required, message: message, title: title, severity: .violation,
                counterpartRuleID: "ADA2010-\(section)"
            ),
        ]
    }

    private static func question(_ section: String, _ subject: String, _ prompt: String, ask: FindingAsk? = nil) -> [Finding] {
        [
            Finding(ruleID: "ADA2010-\(section)", jurisdiction: .ada2010, section: section, subjectID: subject, status: .needsInfo, measured: nil, required: "Yes", message: prompt, ask: ask),
            Finding(ruleID: "CBC11B-\(section)", jurisdiction: .cbc11b, section: "11B-\(section)", subjectID: subject, status: .needsInfo, measured: nil, required: "Yes", message: prompt, ask: ask),
        ]
    }
}
