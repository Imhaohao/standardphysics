import Foundation

/// ADA and CBC state limits in inches, so lengths are shown in inches whatever unit they arrive in.
nonisolated enum MeasurementFormat {
    private static let metresPerInch = 0.0254
    private static let unitSymbols = ["deg": "°", "percent": "%", "%": "%"]

    static func displayValue(_ measured: MeasuredValue) -> Double {
        switch measured.unit {
        case "m": measured.value / metresPerInch
        case "mm": measured.value / 1000 / metresPerInch
        default: measured.value
        }
    }

    static func displayUnit(_ measured: MeasuredValue) -> String {
        ["m", "mm", "in"].contains(measured.unit) ? "in" : measured.unit
    }

    static func string(_ measured: MeasuredValue) -> String {
        let number = trimmed(displayValue(measured))
        let unit = displayUnit(measured)
        if let symbol = unitSymbols[unit] { return number + symbol }
        return "\(number) \(unit)"
    }

    static func trimmed(_ value: Double) -> String {
        let rounded = (value * 10).rounded() / 10
        return rounded == rounded.rounded() ? String(Int(rounded)) : String(format: "%.1f", rounded)
    }
}
