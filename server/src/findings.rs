use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use utoipa::ToSchema;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum FindingStatus {
    Pass,
    Fail,
    NeedsInfo,
    NotApplicable,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Measured {
    pub value: f64,
    pub unit: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Finding {
    pub rule_id: String,
    pub jurisdiction: String,
    pub section: String,
    pub subject_id: String,
    pub status: FindingStatus,
    pub measured: Option<Measured>,
    #[schema(value_type = Option<Object>)]
    pub required: Option<Value>,
    pub message: String,
    #[schema(value_type = Option<Object>)]
    pub evidence: Option<Value>,
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct StatusCounts {
    pub pass: u32,
    pub fail: u32,
    pub needs_info: u32,
    pub not_applicable: u32,
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct Summary {
    pub total: StatusCounts,
    pub by_jurisdiction: BTreeMap<String, StatusCounts>,
}

impl StatusCounts {
    fn add(&mut self, status: FindingStatus) {
        match status {
            FindingStatus::Pass => self.pass += 1,
            FindingStatus::Fail => self.fail += 1,
            FindingStatus::NeedsInfo => self.needs_info += 1,
            FindingStatus::NotApplicable => self.not_applicable += 1,
        }
    }
}

pub fn summarize(findings: &[Finding]) -> Summary {
    let mut summary = Summary::default();
    for finding in findings {
        summary.total.add(finding.status);
        summary
            .by_jurisdiction
            .entry(finding.jurisdiction.clone())
            .or_default()
            .add(finding.status);
    }
    summary
}

pub fn needs_info_finding(rule_id: &str, subject_id: &str, message: &str) -> Finding {
    Finding {
        rule_id: rule_id.to_string(),
        jurisdiction: "SYSTEM".to_string(),
        section: String::new(),
        subject_id: subject_id.to_string(),
        status: FindingStatus::NeedsInfo,
        measured: None,
        required: None,
        message: message.to_string(),
        evidence: None,
    }
}
