//! Unit handling. The scene is in metres/radians; rules are usually in inches. Every conversion
//! goes through [`Unit::convert`], so no other module multiplies by 39.37.

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::fmt;

pub const METRES_PER_INCH: f64 = 0.0254;

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Unit {
    Metre,
    Centimetre,
    Millimetre,
    Inch,
    Foot,
    SquareMetre,
    SquareInch,
    SquareFoot,
    Degree,
    Radian,
    Percent,
    Ratio,
    PoundForce,
    Newton,
    Second,
    Count,
    Boolean,
    Text,
    Other(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Dimension {
    Length,
    Area,
    Angle,
    Slope,
    Force,
    Time,
    Count,
    Boolean,
    Text,
    Unknown,
}

impl Unit {
    /// Parse the unit spellings used by rule and catalog authors. Unknown strings are kept verbatim.
    pub fn parse(raw: &str) -> Unit {
        let key = raw.trim().to_ascii_lowercase();
        lookup_unit(&key).unwrap_or(Unit::Other(raw.trim().to_string()))
    }

    fn dimension(&self) -> Dimension {
        use Unit::*;
        match self {
            Metre | Centimetre | Millimetre | Inch | Foot => Dimension::Length,
            SquareMetre | SquareInch | SquareFoot => Dimension::Area,
            Degree | Radian => Dimension::Angle,
            Percent | Ratio => Dimension::Slope,
            PoundForce | Newton => Dimension::Force,
            Second => Dimension::Time,
            Count => Dimension::Count,
            Boolean => Dimension::Boolean,
            Text => Dimension::Text,
            Other(_) => Dimension::Unknown,
        }
    }

    /// Multiplier from this unit to its dimension's base unit (metre, m², radian, ratio, newton, second).
    fn to_base(&self) -> f64 {
        use Unit::*;
        match self {
            Centimetre => 0.01,
            Millimetre => 0.001,
            Inch => METRES_PER_INCH,
            Foot => METRES_PER_INCH * 12.0,
            SquareInch => METRES_PER_INCH * METRES_PER_INCH,
            SquareFoot => (METRES_PER_INCH * 12.0).powi(2),
            Degree => std::f64::consts::PI / 180.0,
            Percent => 0.01,
            PoundForce => 4.448_221_615_260_5,
            _ => 1.0,
        }
    }

    pub fn is_compatible(&self, other: &Unit) -> bool {
        let (a, b) = (self.dimension(), other.dimension());
        if a == Dimension::Unknown || b == Dimension::Unknown {
            return self == other;
        }
        a == b
    }

    /// Convert `value` from `self` to `target`, or `None` when the dimensions differ.
    pub fn convert(&self, value: f64, target: &Unit) -> Option<f64> {
        if !self.is_compatible(target) {
            return None;
        }
        Some(value * self.to_base() / target.to_base())
    }

    pub fn symbol(&self) -> String {
        use Unit::*;
        let s = match self {
            Metre => "m",
            Centimetre => "cm",
            Millimetre => "mm",
            Inch => "in",
            Foot => "ft",
            SquareMetre => "m2",
            SquareInch => "sq_in",
            SquareFoot => "sq_ft",
            Degree => "deg",
            Radian => "rad",
            Percent => "percent",
            Ratio => "ratio",
            PoundForce => "lbf",
            Newton => "N",
            Second => "s",
            Count => "count",
            Boolean => "bool",
            Text => "text",
            Other(raw) => raw.as_str(),
        };
        s.to_string()
    }
}

fn lookup_unit(key: &str) -> Option<Unit> {
    use Unit::*;
    let unit = match key {
        "m" | "metre" | "meter" | "metres" | "meters" => Metre,
        "cm" | "centimetre" | "centimeter" | "centimetres" | "centimeters" => Centimetre,
        "mm" | "millimetre" | "millimeter" | "millimetres" | "millimeters" => Millimetre,
        "in" | "inch" | "inches" | "\"" => Inch,
        "ft" | "foot" | "feet" | "'" => Foot,
        "m2" | "m^2" | "sq_m" | "square_metres" | "square_meters" => SquareMetre,
        "in2" | "in^2" | "sq_in" | "square_inches" => SquareInch,
        "ft2" | "ft^2" | "sq_ft" | "square_feet" => SquareFoot,
        "deg" | "degree" | "degrees" | "°" => Degree,
        "rad" | "radian" | "radians" => Radian,
        "%" | "percent" | "pct" => Percent,
        "ratio" | "slope" | "fraction" | "rise_over_run" => Ratio,
        "lbf" | "lb" | "lbs" | "pound" | "pounds" | "pound_force" | "pounds_force" => PoundForce,
        "n" | "newton" | "newtons" => Newton,
        "s" | "sec" | "second" | "seconds" => Second,
        "count" | "number" | "n_items" | "items" | "integer" | "int" => Count,
        "bool" | "boolean" | "yes_no" | "present" | "presence" => Boolean,
        "text" | "string" | "enum" | "category" => Text,
        _ => return None,
    };
    Some(unit)
}

impl fmt::Display for Unit {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.symbol())
    }
}

/// A number with its unit.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Quantity {
    pub value: f64,
    pub unit: Unit,
}

impl Quantity {
    pub fn new(value: f64, unit: Unit) -> Self {
        Self { value, unit }
    }

    pub fn metres(value: f64) -> Self {
        Self::new(value, Unit::Metre)
    }

    pub fn to(&self, unit: &Unit) -> Option<Quantity> {
        self.unit.convert(self.value, unit).map(|v| Quantity::new(v, unit.clone()))
    }
}

pub fn inches(value: f64) -> f64 {
    value * METRES_PER_INCH
}

pub fn to_inches(metres: f64) -> f64 {
    metres / METRES_PER_INCH
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn metres_to_inches() {
        let v = Unit::Metre.convert(0.9144, &Unit::Inch).unwrap();
        assert!((v - 36.0).abs() < 1e-9);
    }

    #[test]
    fn slope_percent_and_ratio() {
        let v = Unit::Percent.convert(8.33, &Unit::Ratio).unwrap();
        assert!((v - 0.0833).abs() < 1e-12);
    }

    #[test]
    fn incompatible_units_do_not_convert() {
        assert_eq!(Unit::Inch.convert(1.0, &Unit::PoundForce), None);
        assert_eq!(Unit::parse("furlongs"), Unit::Other("furlongs".into()));
    }

    #[test]
    fn parses_common_spellings() {
        assert_eq!(Unit::parse("Inches"), Unit::Inch);
        assert_eq!(Unit::parse("lbf"), Unit::PoundForce);
        assert_eq!(Unit::parse("%"), Unit::Percent);
    }
}
