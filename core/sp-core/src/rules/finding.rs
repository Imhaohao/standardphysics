use crate::geometry::Vec3;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Pass,
    Fail,
    NeedsInfo,
    NotApplicable,
}

impl Status {
    /// Severity order used when the stricter result governs.
    pub fn rank(self) -> u8 {
        match self {
            Status::NotApplicable => 0,
            Status::Pass => 1,
            Status::NeedsInfo => 2,
            Status::Fail => 3,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Status::Pass => "pass",
            Status::Fail => "fail",
            Status::NeedsInfo => "needs_info",
            Status::NotApplicable => "not_applicable",
        }
    }
}

/// A measured value as the rule compares it, in the rule's unit.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MeasuredValue {
    /// Human-readable value, e.g. "42" or "33.5-34.5" or "yes".
    pub text: String,
    /// The number compared (for a range, the end nearer the limit), if numeric.
    pub value: Option<f64>,
    pub lo: Option<f64>,
    pub hi: Option<f64>,
    pub unit: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Finding {
    pub rule_id: String,
    pub jurisdiction: String,
    pub section: String,
    pub title: String,
    pub subject_id: String,
    pub room_id: Option<String>,
    pub status: Status,
    pub measured: Option<MeasuredValue>,
    pub required: String,
    pub message: String,
    /// The rule's evidence kind plus where the value came from (geometry / observation id).
    pub evidence: String,
    pub severity: String,
    pub location: Option<Vec3>,
    pub counterpart: Option<String>,
    /// The owner question or photo request that would settle a `needs_info` finding.
    #[serde(default)]
    pub ask: Option<Ask>,
}

/// What to ask the owner so a missing answer can be recorded as an owner observation on
/// `subject_id` under `metric`. ADA and CBC findings that share both ask the same question.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Ask {
    pub subject_id: String,
    pub metric: String,
    pub prompt: String,
    pub value_type: String,
    pub unit: String,
    pub options: Vec<String>,
    pub photo: bool,
}
