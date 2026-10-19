//! Metric extraction: one extractor per measured metric in `rules/metrics.json`; photo and owner
//! metrics come from `Scene.observations`.

mod catalog;
mod context;
mod extract;
mod registry;
mod resolve;
pub mod subject;
mod value;

pub use catalog::{Catalog, CategoryDef, Evidence, MetricDef, ValueType};
pub use context::{EvalContext, SubjectOutcome};
pub use extract::support::LEVEL_FLOOR_ASSUMED;
pub use registry::{Extractor, MetricSource, extractor, metric_source, registered_metric_ids};
pub use resolve::resolve;
pub use subject::{Subject, SubjectRef, Tagging, enumerate_subjects};
pub use value::{Extraction, Measurement, Provenance, Value, format_number};
