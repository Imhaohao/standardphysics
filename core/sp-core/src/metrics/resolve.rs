//! Combine geometry and observations into one value per (subject, metric), in the catalog's unit.

use super::registry::extractor;
use super::subject::Subject;
use super::value::{Extraction, Measurement, Provenance, Value};
use super::{EvalContext, MetricDef};
use crate::scene::{Observation, ObservationSource, ObservationValue};
use crate::units::Unit;

/// Order of trust: a tape measure or owner answer, then exact geometry, then a photo label, then
/// geometry that only bounds the value, then nothing.
pub fn resolve(ctx: &EvalContext, subject: &Subject, metric: &MetricDef) -> Extraction {
    let unit = metric.unit();
    let observed = ctx.observation(&subject.id, &metric.id).map(|o| observation_measurement(o, &unit));
    if let Some(m) = observed.as_ref().filter(|m| !is_photo(m)) {
        return in_unit(Extraction::Measured(m.clone()), &unit);
    }
    let geometric = extractor(&metric.id).map(|f| in_unit(f(ctx, subject), &unit));
    match (geometric, observed) {
        (Some(Extraction::Measured(m)), _) if m.value.is_exact() => Extraction::Measured(m),
        (_, Some(photo)) => in_unit(Extraction::Measured(photo), &unit),
        (Some(other), None) => other,
        (None, None) => Extraction::unknown(missing_observation_reason(metric)),
    }
}

fn is_photo(m: &Measurement) -> bool {
    matches!(m.provenance, Provenance::Observation { source: ObservationSource::Photo, .. })
}

fn missing_observation_reason(metric: &MetricDef) -> String {
    match metric.evidence {
        super::Evidence::Owner => format!("needs an answer from the owner ({})", metric.id),
        super::Evidence::Photo => format!("needs a photo of the element ({})", metric.id),
        super::Evidence::Measured => format!("no extractor for {}", metric.id),
    }
}

fn in_unit(extraction: Extraction, unit: &Unit) -> Extraction {
    match extraction {
        Extraction::Measured(m) => match m.converted_to(unit) {
            Some(converted) => Extraction::Measured(converted),
            None => Extraction::unknown(format!("value in {} cannot be compared in {}", m.unit, unit)),
        },
        other => other,
    }
}

fn observation_measurement(observation: &Observation, catalog_unit: &Unit) -> Measurement {
    let unit = observation.unit.as_deref().map(Unit::parse).unwrap_or_else(|| catalog_unit.clone());
    let value = match &observation.value {
        ObservationValue::Number(n) => Value::exact(*n),
        ObservationValue::Bool(b) => Value::Bool { value: *b },
        ObservationValue::Text(t) => text_value(t),
    };
    let unit = if matches!(value, Value::Number { .. }) { unit } else { catalog_unit.clone() };
    Measurement {
        value,
        unit,
        provenance: Provenance::Observation { id: observation.id.clone(), source: observation.source },
        confidence: observation.confidence,
        location: None,
        note: None,
    }
}

/// Owners answer "yes"/"no" in text; keep anything else verbatim.
fn text_value(text: &str) -> Value {
    match text.trim().to_ascii_lowercase().as_str() {
        "yes" | "true" | "y" => Value::Bool { value: true },
        "no" | "false" | "n" => Value::Bool { value: false },
        _ => Value::Text { value: text.to_string() },
    }
}
