use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
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
    pub text: String,
    pub value: Option<f64>,
    pub lo: Option<f64>,
    pub hi: Option<f64>,
    pub unit: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Point3 {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

/// Every value `Finding.severity` can take. `violation` and `advisory` come from the rulepack
/// (`advisory` also replaces `violation` when a level floor is only assumed); `info` is used
/// by server-generated findings such as unresolved labels.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    Violation,
    Advisory,
    Info,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Finding {
    pub rule_id: String,
    pub jurisdiction: String,
    pub section: String,
    pub title: String,
    pub subject_id: String,
    pub room_id: Option<String>,
    pub status: FindingStatus,
    pub measured: Option<Measured>,
    pub required: String,
    pub message: String,
    pub evidence: String,
    #[schema(value_type = Severity)]
    pub severity: String,
    pub location: Option<Point3>,
    pub counterpart: Option<String>,
    /// The owner question or photo request that would settle this `needs_info` finding.
    /// ADA and CBC findings with the same `subject_id` and `metric` are one question.
    #[serde(default)]
    pub ask: Option<Ask>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Ask {
    /// Record the answer on this subject (the site for site-wide questions).
    pub subject_id: String,
    pub metric: String,
    pub prompt: String,
    /// `boolean`, `number`, `integer`, `enum` or `text`.
    pub value_type: String,
    /// Unit a number answer is given in, e.g. `lbf` or `in`.
    pub unit: String,
    /// Allowed values when `value_type` is `enum`.
    pub options: Vec<String>,
    /// The rule wants a photo; the owner may still answer directly.
    pub photo: bool,
}

impl Ask {
    fn from_core(a: &sp_core::rules::Ask) -> Self {
        Self {
            subject_id: a.subject_id.clone(),
            metric: a.metric.clone(),
            prompt: a.prompt.clone(),
            value_type: a.value_type.clone(),
            unit: a.unit.clone(),
            options: a.options.clone(),
            photo: a.photo,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct Governing {
    pub subject_id: String,
    pub status: FindingStatus,
    pub governing_rule_id: String,
    pub governing_jurisdiction: String,
    pub rule_ids: Vec<String>,
    pub message: String,
}

pub struct EvaluationReport {
    pub findings: Vec<Finding>,
    pub governing: Vec<Governing>,
    pub governing_counts: StatusCounts,
}

impl FindingStatus {
    fn from_core(status: sp_core::rules::Status) -> Self {
        use sp_core::rules::Status;
        match status {
            Status::Pass => Self::Pass,
            Status::Fail => Self::Fail,
            Status::NeedsInfo => Self::NeedsInfo,
            Status::NotApplicable => Self::NotApplicable,
        }
    }
}

impl Finding {
    pub fn from_core(f: &sp_core::rules::Finding) -> Self {
        Self {
            rule_id: f.rule_id.clone(),
            jurisdiction: f.jurisdiction.clone(),
            section: f.section.clone(),
            title: f.title.clone(),
            subject_id: f.subject_id.clone(),
            room_id: f.room_id.clone(),
            status: FindingStatus::from_core(f.status),
            measured: f.measured.as_ref().map(|m| Measured {
                text: m.text.clone(),
                value: m.value,
                lo: m.lo,
                hi: m.hi,
                unit: m.unit.clone(),
            }),
            required: f.required.clone(),
            message: f.message.clone(),
            evidence: f.evidence.clone(),
            severity: f.severity.clone(),
            location: f.location.map(|p| Point3 {
                x: p.x,
                y: p.y,
                z: p.z,
            }),
            counterpart: f.counterpart.clone(),
            ask: f.ask.as_ref().map(Ask::from_core),
        }
    }
}

impl Governing {
    pub fn from_core(g: &sp_core::rules::GoverningFinding) -> Self {
        Self {
            subject_id: g.subject_id.clone(),
            status: FindingStatus::from_core(g.status),
            governing_rule_id: g.governing_rule_id.clone(),
            governing_jurisdiction: g.governing_jurisdiction.clone(),
            rule_ids: g.rule_ids.clone(),
            message: g.message.clone(),
        }
    }
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
    #[serde(default)]
    pub governing_counts: StatusCounts,
    #[serde(default)]
    pub governing: Vec<Governing>,
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
        title: "Object not identified".to_string(),
        room_id: None,
        measured: None,
        required: String::new(),
        message: message.to_string(),
        evidence: "vision".to_string(),
        severity: "info".to_string(),
        location: None,
        counterpart: None,
        ask: None,
    }
}
