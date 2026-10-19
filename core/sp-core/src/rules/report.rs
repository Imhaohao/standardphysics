//! Per-jurisdiction reports and the governing (stricter) result across jurisdictions.

use super::finding::{Finding, Status};
use super::model::Rule;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct StatusCounts {
    pub pass: usize,
    pub fail: usize,
    pub needs_info: usize,
    pub not_applicable: usize,
}

impl StatusCounts {
    fn add(&mut self, status: Status) {
        match status {
            Status::Pass => self.pass += 1,
            Status::Fail => self.fail += 1,
            Status::NeedsInfo => self.needs_info += 1,
            Status::NotApplicable => self.not_applicable += 1,
        }
    }

    pub fn of<'a>(statuses: impl Iterator<Item = Status> + 'a) -> Self {
        let mut counts = Self::default();
        statuses.for_each(|s| counts.add(s));
        counts
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct JurisdictionReport {
    pub jurisdiction: String,
    pub counts: StatusCounts,
    pub findings: Vec<Finding>,
}

/// One requirement on one subject across jurisdictions: the stricter (worse) result governs.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GoverningFinding {
    pub subject_id: String,
    pub status: Status,
    pub governing_rule_id: String,
    pub governing_jurisdiction: String,
    pub rule_ids: Vec<String>,
    pub message: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Report {
    pub jurisdictions: Vec<JurisdictionReport>,
    pub governing: Vec<GoverningFinding>,
    pub governing_counts: StatusCounts,
}

impl Report {
    pub fn build(findings: Vec<Finding>, rules: &HashMap<String, &Rule>) -> Report {
        let governing = governing(&findings, rules);
        let mut by_jurisdiction: BTreeMap<String, Vec<Finding>> = BTreeMap::new();
        for f in findings {
            by_jurisdiction.entry(f.jurisdiction.clone()).or_default().push(f);
        }
        let jurisdictions = by_jurisdiction
            .into_iter()
            .map(|(jurisdiction, findings)| JurisdictionReport { counts: StatusCounts::of(findings.iter().map(|f| f.status)), jurisdiction, findings })
            .collect();
        Report { governing_counts: StatusCounts::of(governing.iter().map(|g| g.status)), jurisdictions, governing }
    }
}

/// Requirement key shared by a rule and its counterpart: the lexically smaller of the two ids.
fn requirement_key(finding: &Finding) -> String {
    match &finding.counterpart {
        Some(other) if other < &finding.rule_id => other.clone(),
        _ => finding.rule_id.clone(),
    }
}

fn governing(findings: &[Finding], rules: &HashMap<String, &Rule>) -> Vec<GoverningFinding> {
    let mut groups: BTreeMap<(String, String), Vec<&Finding>> = BTreeMap::new();
    for f in findings {
        groups.entry((f.subject_id.clone(), requirement_key(f))).or_default().push(f);
    }
    groups.into_values().map(|group| govern(&group, rules)).collect()
}

/// Worst status wins; among equals, the rule declared stricter than the others wins.
fn govern(group: &[&Finding], rules: &HashMap<String, &Rule>) -> GoverningFinding {
    let stricter = |f: &Finding| rules.get(&f.rule_id).is_some_and(|r| group.iter().any(|g| r.stricter_than.contains(&g.rule_id)));
    let winner = group
        .iter()
        .max_by_key(|f| (f.status.rank(), stricter(f), f.jurisdiction.clone()))
        .copied()
        .expect("groups are never empty");
    GoverningFinding {
        subject_id: winner.subject_id.clone(),
        status: winner.status,
        governing_rule_id: winner.rule_id.clone(),
        governing_jurisdiction: winner.jurisdiction.clone(),
        rule_ids: group.iter().map(|f| f.rule_id.clone()).collect(),
        message: winner.message.clone(),
    }
}
