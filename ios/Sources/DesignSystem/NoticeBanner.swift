import SwiftUI

/// Something that didn't go through, with a way to put it away.
struct NoticeBanner: View {
    let message: String
    let onDismiss: () -> Void

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s) {
            Image(systemName: "exclamationmark.circle.fill")
                .foregroundStyle(Theme.Palette.problem)
                .accessibilityHidden(true)
            Text(message)
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: Theme.Spacing.s)
            Button("Dismiss", action: onDismiss)
                .buttonStyle(InkButtonStyle(variant: .quiet, height: Theme.Size.compactControl))
        }
        .padding(.leading, Theme.Spacing.s + 4)
        .padding(.vertical, Theme.Spacing.xs)
        .background(RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous).fill(Theme.Palette.problemWash))
        .accessibilityElement(children: .contain)
    }
}

#Preview {
    NoticeBanner(message: "We couldn't delete this from your account, so it's still here. Check your connection and try again.") {}
        .padding()
        .background(PaperBackground())
}
