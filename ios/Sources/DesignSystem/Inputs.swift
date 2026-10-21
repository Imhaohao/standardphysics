import SwiftUI

/// A labelled text field. The label stays visible above the field, so the placeholder is only
/// ever an example of the format.
struct InkTextField: View {
    enum Kind {
        case email
        case newPassword
        case password
        case number
    }

    let label: String
    @Binding var text: String
    var kind: Kind = .email
    var prompt: String?

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Text(label)
                .font(Theme.Typography.callout.weight(.bold))
                .foregroundStyle(Theme.Palette.ink)
            field
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Palette.ink)
                .padding(.horizontal, Theme.Spacing.s + 4)
                .frame(minHeight: Theme.Size.compactControl)
                .background {
                    let shape = RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous)
                    shape.fill(Theme.Palette.sheet)
                        .overlay(shape.stroke(Theme.Palette.rule, lineWidth: Theme.Stroke.hairline))
                }
                .accessibilityLabel(label)
        }
    }

    @ViewBuilder private var field: some View {
        switch kind {
        case .email:
            TextField(label, text: $text, prompt: Text(prompt ?? ""))
                .textContentType(.username)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
        case .password, .newPassword:
            SecureField(label, text: $text, prompt: Text(prompt ?? ""))
                .textContentType(kind == .newPassword ? .newPassword : .password)
        case .number:
            TextField(label, text: $text, prompt: Text(prompt ?? ""))
                .keyboardType(.decimalPad)
                .font(Theme.Typography.measurement)
                .monospacedDigit()
        }
    }
}

#Preview {
    @Previewable @State var email = ""
    @Previewable @State var password = ""
    VStack(spacing: Theme.Spacing.m) {
        InkTextField(label: "Email", text: $email, prompt: "name@example.com")
        InkTextField(label: "Password", text: $password, kind: .password)
    }
    .padding()
    .background(PaperBackground())
}
