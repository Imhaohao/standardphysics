import SwiftUI

struct RoomFinishedSheet: View {
    @Environment(AppModel.self) private var model
    @State private var roomName = ""
    @FocusState private var isNameFocused: Bool

    private let suggestions = ["Sales floor", "Entrance", "Restroom", "Dining room", "Fitting room", "Back room"]

    private var lastRoom: RoomRecord? { model.capture.manifest?.rooms.last }

    var body: some View {
        ZStack {
            PaperBackground(showsGrid: false)
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                    VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                        InkedTitle(text: "Room \(lastRoom?.index ?? 1) is saved")
                        RoomSlots(saved: model.completedRooms)
                    }
                    nameField
                    actions
                }
                .padding(Theme.Spacing.l)
            }
            .scrollBounceBehavior(.basedOnSize)
        }
        .onAppear { roomName = lastRoom?.name ?? "" }
    }

    private var nameField: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            Text("What do you call this room?")
                .font(Theme.Typography.headline)
                .foregroundStyle(Theme.Palette.ink)
            TextField("Sales floor", text: $roomName)
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Palette.ink)
                .submitLabel(.done)
                .focused($isNameFocused)
                .padding(.horizontal, Theme.Spacing.m)
                .frame(minHeight: Theme.Size.control)
                .background(RoundedRectangle(cornerRadius: Theme.Radius.control).fill(Theme.Palette.sheet))
                .overlay(RoundedRectangle(cornerRadius: Theme.Radius.control).stroke(Theme.Palette.rule, lineWidth: Theme.Stroke.hairline))
            ScrollView(.horizontal) {
                HStack(spacing: Theme.Spacing.s) {
                    ForEach(suggestions, id: \.self) { suggestion in
                        SuggestionChip(title: suggestion, isSelected: roomName == suggestion) { roomName = suggestion }
                    }
                }
            }
            .scrollIndicators(.hidden)
        }
    }

    private var actions: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s + 4) {
            PrimaryButton(title: "Scan another room", systemImage: "plus.viewfinder") {
                Task {
                    await saveName()
                    model.scanAnotherRoom()
                }
            }
            .disabled(!model.canAddRoom)
            if !model.canAddRoom {
                Text("This scan has \(ScanLimits.maxRooms) rooms, the most one scan can hold. Finish it to see your results.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Palette.inkMuted)
            }
            SecondaryButton(title: finishTitle, systemImage: "checkmark.seal") {
                Task {
                    await saveName()
                    await model.finishScan()
                }
            }
        }
    }

    private var finishTitle: String {
        model.completedRooms == 1 ? "Finish and check this room" : "Finish and check \(model.completedRooms) rooms"
    }

    private func saveName() async {
        isNameFocused = false
        guard let index = lastRoom?.index else { return }
        await model.nameRoom(index: index, name: roomName)
    }
}

private struct SuggestionChip: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.xs) {
                if isSelected { Image(systemName: "checkmark").imageScale(.small) }
                Text(title)
            }
            .font(Theme.Typography.callout)
            .foregroundStyle(isSelected ? Theme.Palette.sheet : Theme.Palette.ink)
            .padding(.horizontal, Theme.Spacing.m - 2)
            .frame(minHeight: Theme.Size.compactControl - 8)
            .background(Capsule().fill(isSelected ? Theme.Palette.ink : Theme.Palette.sheet))
            .shadow(color: Theme.Elevation.cardColor, radius: 3, y: 1)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}
