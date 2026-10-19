//! What an extractor returns: a measured value (possibly a range), unknown, or not applicable.

use crate::geometry::Vec3;
use crate::scene::ObservationSource;
use crate::units::Unit;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Value {
    /// A number known to lie in `[lo, hi]`; exact when `lo == hi`. `hi` may be infinite.
    Number { lo: f64, hi: f64 },
    Bool { value: bool },
    Text { value: String },
}

impl Value {
    pub fn exact(value: f64) -> Value {
        Value::Number { lo: value, hi: value }
    }

    pub fn range(lo: f64, hi: f64) -> Value {
        Value::Number { lo: lo.min(hi), hi: lo.max(hi) }
    }

    pub fn is_exact(&self) -> bool {
        match self {
            Value::Number { lo, hi } => lo == hi,
            _ => true,
        }
    }

    fn scaled(&self, from: &Unit, to: &Unit) -> Option<Value> {
        match self {
            Value::Number { lo, hi } => Some(Value::Number { lo: from.convert(*lo, to)?, hi: from.convert(*hi, to)? }),
            other => Some(other.clone()),
        }
    }

    pub fn describe(&self) -> String {
        match self {
            Value::Number { lo, hi } if lo == hi => format_number(*lo),
            Value::Number { lo, hi } if hi.is_infinite() => format!("at least {}", format_number(*lo)),
            Value::Number { lo, hi } => format!("{}-{}", format_number(*lo), format_number(*hi)),
            Value::Bool { value } => if *value { "yes" } else { "no" }.to_string(),
            Value::Text { value } => value.clone(),
        }
    }
}

pub fn format_number(value: f64) -> String {
    let rounded = (value * 100.0).round() / 100.0;
    if rounded.fract() == 0.0 { format!("{rounded:.0}") } else { format!("{rounded}") }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Provenance {
    /// Derived by `sp-core` from scan geometry.
    Geometry,
    Observation { id: String, source: ObservationSource },
}

#[derive(Debug, Clone, PartialEq)]
pub struct Measurement {
    pub value: Value,
    pub unit: Unit,
    pub provenance: Provenance,
    pub confidence: f64,
    pub location: Option<Vec3>,
    pub note: Option<String>,
}

impl Measurement {
    pub fn geometry(value: Value, unit: Unit) -> Self {
        Self { value, unit, provenance: Provenance::Geometry, confidence: 1.0, location: None, note: None }
    }

    pub fn converted_to(&self, unit: &Unit) -> Option<Measurement> {
        if !matches!(self.value, Value::Number { .. }) {
            return Some(Measurement { unit: unit.clone(), ..self.clone() });
        }
        let value = self.value.scaled(&self.unit, unit)?;
        Some(Measurement { value, unit: unit.clone(), ..self.clone() })
    }

    pub fn at(mut self, location: Option<Vec3>) -> Self {
        self.location = location;
        self
    }

    pub fn with_note(mut self, note: impl Into<String>) -> Self {
        self.note = Some(note.into());
        self
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum Extraction {
    Measured(Measurement),
    /// The value cannot be determined from what was captured; the reason says what is missing.
    Unknown(String),
    /// The metric does not apply to this subject (the reason says why).
    NotApplicable(String),
}

impl Extraction {
    pub fn metres(value: f64) -> Self {
        Self::Measured(Measurement::geometry(Value::exact(value), crate::units::Unit::Metre))
    }

    pub fn metres_range(lo: f64, hi: f64) -> Self {
        Self::Measured(Measurement::geometry(Value::range(lo, hi), crate::units::Unit::Metre))
    }

    pub fn boolean(value: bool) -> Self {
        Self::Measured(Measurement::geometry(Value::Bool { value }, crate::units::Unit::Boolean))
    }

    pub fn count(value: usize) -> Self {
        Self::Measured(Measurement::geometry(Value::exact(value as f64), crate::units::Unit::Count))
    }

    pub fn count_range(lo: usize, hi: usize) -> Self {
        Self::Measured(Measurement::geometry(Value::range(lo as f64, hi as f64), crate::units::Unit::Count))
    }

    pub fn ratio(value: f64) -> Self {
        Self::Measured(Measurement::geometry(Value::exact(value), crate::units::Unit::Ratio))
    }

    pub fn text(value: impl Into<String>) -> Self {
        Self::Measured(Measurement::geometry(Value::Text { value: value.into() }, crate::units::Unit::Text))
    }

    pub fn unknown(reason: impl Into<String>) -> Self {
        Self::Unknown(reason.into())
    }

    pub fn not_applicable(reason: impl Into<String>) -> Self {
        Self::NotApplicable(reason.into())
    }

    /// Attach a plan location (at floor height) to a measurement.
    pub fn located(self, location: Option<Vec3>) -> Self {
        match self {
            Self::Measured(m) => Self::Measured(m.at(location)),
            other => other,
        }
    }

    pub fn noted(self, note: impl Into<String>) -> Self {
        match self {
            Self::Measured(m) => Self::Measured(m.with_note(note)),
            other => other,
        }
    }

    pub fn is_known(&self) -> bool {
        matches!(self, Self::Measured(_))
    }

    pub fn measurement(&self) -> Option<&Measurement> {
        match self {
            Self::Measured(m) => Some(m),
            _ => None,
        }
    }
}

/// Lengths in metres, or unknown when absent.
pub fn metres_or_unknown(value: Option<f64>, reason: &str) -> Extraction {
    value.map(Extraction::metres).unwrap_or_else(|| Extraction::unknown(reason))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn converts_ranges_between_units() {
        let m = Measurement::geometry(Value::range(0.9144, 1.0), Unit::Metre).converted_to(&Unit::Inch).unwrap();
        match m.value {
            Value::Number { lo, .. } => assert!((lo - 36.0).abs() < 1e-9),
            _ => panic!(),
        }
        assert_eq!(Value::range(3.0, f64::INFINITY).describe(), "at least 3");
    }
}
