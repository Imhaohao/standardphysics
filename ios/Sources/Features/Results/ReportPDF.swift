import SwiftUI

/// One block of the printed report, in reading order.
nonisolated struct ReportLine: Sendable, Equatable {
    enum Style: Sendable {
        case title
        case room
        case subject
        case body
        case detail
    }

    let style: Style
    let text: String
}

/// What the printed report says: the same grouping as the screen, written out in full.
nonisolated enum ReportOutline {
    static func lines(for report: ScanReport) -> [ReportLine] {
        header(for: report)
            + ReportGrouping.sections(for: report).flatMap { section in lines(for: section, answers: report.answers) }
            + [ReportLine(style: .detail, text: "Standard Physics measured this space from an iPhone scan. Use it as a guide to what to fix, not as a legal certification.")]
    }

    private static func header(for report: ScanReport) -> [ReportLine] {
        let summary = ReportGrouping.summary(for: report)
        let rooms = report.roomNames.count == 1 ? "1 room" : "\(report.roomNames.count) rooms"
        return [
            ReportLine(style: .title, text: report.name),
            ReportLine(style: .detail, text: "\(rooms), checked \(report.completedAt.formatted(date: .long, time: .omitted))"),
            ReportLine(style: .body, text: "\(count(summary.toFix, "thing", "things")) to fix, \(count(summary.questions, "question", "questions")) for you, and \(count(summary.passing, "check", "checks")) passed."),
            ReportLine(style: .detail, text: "Each item was checked against the federal ADA 2010 Standards and California's CBC Chapter 11B. Where the two set different limits, the stricter one applies."),
        ]
    }

    private static func lines(for section: RoomSection, answers: [OwnerAnswer]) -> [ReportLine] {
        var lines = [ReportLine(style: .room, text: section.name)]
        for group in section.objectsWithIssues {
            lines.append(ReportLine(style: .subject, text: group.subject.label))
            lines += group.issues.flatMap { issueLines($0, answers: answers) }
        }
        if !section.passing.isEmpty {
            lines.append(ReportLine(style: .detail, text: "\(count(section.passing.count, "check", "checks")) passed in this room."))
        }
        return lines
    }

    private static func issueLines(_ outcome: RuleOutcome, answers: [OwnerAnswer]) -> [ReportLine] {
        let finding = outcome.governing
        let lead = outcome.isQuestion ? "Question" : "To fix"
        let headline = [finding.title, OwnerQuestions.question(for: outcome)?.ask.prompt ?? finding.message].compactMap { $0 }.joined(separator: ". ")
        return [
            ReportLine(style: .body, text: "\(lead): \(headline)"),
            ReportLine(style: .detail, text: detail(for: outcome, answers: answers)),
        ]
    }

    private static func detail(for outcome: RuleOutcome, answers: [OwnerAnswer]) -> String {
        var parts: [String] = []
        if !outcome.governing.required.isEmpty, !outcome.isQuestion { parts.append("Required \(outcome.governing.required)") }
        if let measured = outcome.governing.measured { parts.append("measured \(MeasurementFormat.string(measured))") }
        if let question = OwnerQuestions.question(for: outcome), let answer = OwnerQuestions.answer(to: question, in: answers) {
            parts.append("your answer \(answerText(answer))")
        }
        parts.append(Citation.list(for: outcome))
        return parts.joined(separator: ", ")
    }

    static func answerText(_ answer: OwnerAnswer) -> String {
        switch answer.value {
        case .bool(let flag): flag ? "yes" : "no"
        case .number(let number): [MeasurementFormat.trimmed(number), answer.unit].compactMap { $0 }.joined(separator: " ")
        case .text(let text): OwnerQuestions.optionTitle(text)
        }
    }

    private static func count(_ number: Int, _ one: String, _ many: String) -> String {
        "\(number) \(number == 1 ? one : many)"
    }
}

/// Letter-size pages with the outline drawn top to bottom; a block that won't fit starts a new page.
enum ReportPDF {
    static let pageSize = CGSize(width: 612, height: 792)
    static let margin: CGFloat = 54

    static func write(_ report: ScanReport) throws -> URL {
        let url = FileManager.default.temporaryDirectory.appending(path: fileName(for: report))
        try data(for: report).write(to: url, options: .atomic)
        return url
    }

    nonisolated static func fileName(for report: ScanReport) -> String {
        let safe = String(report.name.unicodeScalars.map { scalar -> Character in
            CharacterSet.alphanumerics.contains(scalar) || scalar == " " || scalar == "-" ? Character(scalar) : "-"
        }).trimmingCharacters(in: .whitespaces)
        return "\(safe.isEmpty ? "Report" : safe) accessibility report.pdf"
    }

    static func data(for report: ScanReport) -> Data {
        let format = UIGraphicsPDFRendererFormat()
        format.documentInfo = [kCGPDFContextTitle as String: report.name, kCGPDFContextCreator as String: "Standard Physics"]
        let renderer = UIGraphicsPDFRenderer(bounds: CGRect(origin: .zero, size: pageSize), format: format)
        let blocks = ReportOutline.lines(for: report).map(attributed)
        return renderer.pdfData { context in
            draw(blocks, in: context)
        }
    }

    private static func draw(_ blocks: [NSAttributedString], in context: UIGraphicsPDFRendererContext) {
        let width = pageSize.width - margin * 2
        let bottom = pageSize.height - margin
        context.beginPage()
        var y = margin
        for block in blocks {
            let height = ceil(block.boundingRect(with: CGSize(width: width, height: .greatestFiniteMagnitude), options: [.usesLineFragmentOrigin, .usesFontLeading], context: nil).height)
            if y + height > bottom, y > margin {
                context.beginPage()
                y = margin
            }
            block.draw(with: CGRect(x: margin, y: y, width: width, height: height), options: [.usesLineFragmentOrigin, .usesFontLeading], context: nil)
            y += height + spacing(after: block)
        }
    }

    private static func spacing(after block: NSAttributedString) -> CGFloat {
        (block.attribute(.paragraphSpacingAfterKey, at: 0, effectiveRange: nil) as? CGFloat) ?? 6
    }

    private static func attributed(_ line: ReportLine) -> NSAttributedString {
        let style = textStyle(line.style)
        return NSAttributedString(string: line.text, attributes: [
            .font: style.font,
            .foregroundColor: style.color,
            .paragraphSpacingAfterKey: style.spacingAfter,
        ])
    }

    private static func textStyle(_ style: ReportLine.Style) -> (font: UIFont, color: UIColor, spacingAfter: CGFloat) {
        switch style {
        case .title: (font(Theme.Typography.displayFamily, 26, .heavy), UIColor(Theme.Palette.ink), 6)
        case .room: (font(Theme.Typography.displayFamily, 17, .bold), UIColor(Theme.Palette.ink), 8)
        case .subject: (font(Theme.Typography.bodyFamily, 13, .bold), UIColor(Theme.Palette.ink), 4)
        case .body: (font(Theme.Typography.bodyFamily, 11, .regular), UIColor(Theme.Palette.ink), 2)
        case .detail: (font(Theme.Typography.bodyFamily, 9.5, .regular), UIColor(Theme.Palette.inkMuted), 10)
        }
    }

    private static func font(_ family: String, _ size: CGFloat, _ weight: UIFont.Weight) -> UIFont {
        let descriptor = UIFontDescriptor(fontAttributes: [.family: family])
            .addingAttributes([.traits: [UIFontDescriptor.TraitKey.weight: weight]])
        return UIFont(descriptor: descriptor, size: size)
    }
}

extension NSAttributedString.Key {
    /// Space below a printed block, carried with its text so the layout loop needs no lookup.
    static let paragraphSpacingAfterKey = NSAttributedString.Key("SPParagraphSpacingAfter")
}
