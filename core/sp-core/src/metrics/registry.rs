//! Metric id to extractor. Photo and owner metrics without a geometric fallback map to
//! [`MetricSource::NeedsObservation`].

use super::extract;
use super::subject::Subject;
use super::value::Extraction;
use super::{EvalContext, MetricDef};
use std::collections::HashMap;
use std::sync::OnceLock;

pub type Extractor = fn(&EvalContext, &Subject) -> Extraction;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MetricSource {
    /// Derived (or bounded) from scan geometry, with observations taking precedence when present.
    Extractor,
    /// Comes only from `Scene.observations` (photo labels and owner answers).
    NeedsObservation,
    /// A measured metric with no extractor: a catalog/engine mismatch.
    Missing,
}

fn table() -> &'static HashMap<&'static str, Extractor> {
    static TABLE: OnceLock<HashMap<&'static str, Extractor>> = OnceLock::new();
    TABLE.get_or_init(|| extract::ALL.iter().flat_map(|group| group.iter()).map(|(id, f)| (*id, *f)).collect())
}

pub fn extractor(metric_id: &str) -> Option<Extractor> {
    table().get(metric_id).copied()
}

pub fn registered_metric_ids() -> Vec<&'static str> {
    let mut ids: Vec<&'static str> = table().keys().copied().collect();
    ids.sort_unstable();
    ids
}

pub fn metric_source(metric: &MetricDef) -> MetricSource {
    match (extractor(&metric.id).is_some(), metric.needs_observation()) {
        (true, _) => MetricSource::Extractor,
        (false, true) => MetricSource::NeedsObservation,
        (false, false) => MetricSource::Missing,
    }
}
