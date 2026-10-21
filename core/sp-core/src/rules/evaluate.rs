//! Evaluate one rule against one subject.

use super::finding::{Ask, Finding, MeasuredValue, Status};
use super::model::{Answer, Comparison, Condition, Op, Operand, Rule, TableRow, Test, WhenUnknown};
use crate::geometry::Vec3;
use crate::metrics::subject::{Subject, SubjectRef};
use crate::metrics::{
    EvalContext, Extraction, LEVEL_FLOOR_ASSUMED, Measurement, MetricDef, Provenance, Value, ValueType, format_number,
    resolve,
};

const ADVISORY: &str = "advisory";
use crate::units::Unit;
use serde_json::Value as Json;
use std::cell::RefCell;
use std::collections::HashMap;

/// Result of a test before it becomes a finding.
#[derive(Debug, Clone)]
struct Outcome {
    status: Status,
    measured: Option<MeasuredValue>,
    required: String,
    reason: Option<String>,
    location: Option<Vec3>,
    provenance: Option<String>,
    ask: Option<Ask>,
}

impl Outcome {
    fn new(status: Status, required: String) -> Self {
        Self { status, measured: None, required, reason: None, location: None, provenance: None, ask: None }
    }

    fn because(mut self, reason: impl Into<String>) -> Self {
        self.reason = Some(reason.into());
        self
    }
}

/// Three-valued truth for scoping conditions.
#[derive(Debug, Clone, PartialEq)]
enum Truth {
    Yes,
    No,
    Unknown(String),
}

pub struct Evaluator<'a> {
    ctx: &'a EvalContext<'a>,
    site: &'a Subject,
    cache: RefCell<HashMap<(String, String), Extraction>>,
}

impl<'a> Evaluator<'a> {
    pub fn new(ctx: &'a EvalContext<'a>, site: &'a Subject) -> Self {
        Self { ctx, site, cache: RefCell::new(HashMap::new()) }
    }

    /// Resolve a metric, on the site when the catalog says it is a site metric.
    fn metric(&self, subject: &Subject, metric_id: &str) -> Extraction {
        let Some(def) = self.ctx.catalog.metric(metric_id) else {
            return Extraction::unknown(format!("metric {metric_id} is not in the catalog"));
        };
        let target = self.site_or(subject, def);
        let key = (target.id.clone(), metric_id.to_string());
        if let Some(hit) = self.cache.borrow().get(&key) {
            return hit.clone();
        }
        let value = resolve(self.ctx, target, def);
        self.cache.borrow_mut().insert(key, value.clone());
        value
    }

    fn site_or<'s>(&'s self, subject: &'s Subject, def: &MetricDef) -> &'s Subject {
        let is_site_metric = def.element == "site" || def.id.starts_with("site.");
        let belongs_to_site =
            subject.reference != SubjectRef::Site && !def.applies_to.iter().any(|t| subject.has_tag(t));
        if is_site_metric && belongs_to_site { self.site } else { subject }
    }

    /// The subject a metric is recorded on: the site for site metrics, else the subject itself.
    fn metric_target<'s>(&'s self, subject: &'s Subject, metric_id: &str) -> &'s Subject {
        match self.ctx.catalog.metric(metric_id) {
            Some(def) => self.site_or(subject, def),
            None => subject,
        }
    }

    pub fn evaluate(&self, rule: &Rule, subject: &Subject) -> Finding {
        let outcome = match self.scope(rule, subject) {
            Some(skip) => skip,
            None => self.test(&rule.test, rule, subject),
        };
        finding(rule, subject, outcome)
    }

    fn scope(&self, rule: &Rule, subject: &Subject) -> Option<Outcome> {
        let when = rule.scoping.when.as_ref()?;
        match self.condition(when, subject) {
            Truth::Yes => None,
            Truth::No => Some(
                Outcome::new(Status::NotApplicable, String::new())
                    .because(format!("out of scope: {}", rule.scoping.text)),
            ),
            Truth::Unknown(reason) => match rule.scoping.when_unknown {
                WhenUnknown::Apply => None,
                WhenUnknown::NotApplicable => Some(Outcome::new(Status::NotApplicable, String::new()).because(reason)),
                WhenUnknown::NeedsInfo => Some(
                    Outcome::new(Status::NeedsInfo, rule.scoping.text.clone())
                        .because(format!("scope unknown: {reason}")),
                ),
            },
        }
    }

    fn condition(&self, condition: &Condition, subject: &Subject) -> Truth {
        match condition {
            Condition::Compare(c) => self.compare_truth(c, subject),
            Condition::All(items) => all_truth(items.iter().map(|c| self.condition(c, subject))),
            Condition::Any(items) => any_truth(items.iter().map(|c| self.condition(c, subject))),
            Condition::Not(inner) => match self.condition(inner, subject) {
                Truth::Yes => Truth::No,
                Truth::No => Truth::Yes,
                unknown => unknown,
            },
            Condition::CategoryPresent(category) => yes_no(self.category_present(category)),
            Condition::RoomKindIn(kinds) => self.room_kind_in(kinds, subject),
            Condition::SubjectCategoryIn(categories) => yes_no(categories.iter().any(|c| subject.has_tag(c))),
            Condition::Unsupported(json) => Truth::Unknown(format!("unsupported scoping condition {json}")),
        }
    }

    /// Site metrics are defined everywhere; others only for the categories in their `applies_to`.
    fn defined_for(&self, metric_id: &str, subject: &Subject) -> bool {
        let Some(def) = self.ctx.catalog.metric(metric_id) else { return true };
        def.element == "site" || metric_id.starts_with("site.") || def.applies_to.iter().any(|t| subject.has_tag(t))
    }

    fn category_present(&self, category: &str) -> bool {
        self.ctx
            .objects()
            .any(|(_, o)| o.category == category || self.ctx.catalog.canonical_category(&o.category) == Some(category))
    }

    fn room_kind_in(&self, kinds: &[String], subject: &Subject) -> Truth {
        let Some(room) = self.ctx.room(subject) else { return Truth::Unknown("subject is not in a room".into()) };
        let kind = room.kind.as_str();
        let alias = if room.kind == crate::scene::RoomKind::Restroom { "toilet_room" } else { kind };
        yes_no(kinds.iter().any(|k| k == kind || k == alias))
    }

    fn compare_truth(&self, comparison: &Comparison, subject: &Subject) -> Truth {
        if !self.defined_for(&comparison.metric, subject) {
            return Truth::No;
        }
        let unit = self.ctx.catalog.metric(&comparison.metric).map(|m| m.unit()).unwrap_or(Unit::Text);
        let outcome = self.compare(comparison, &unit, None, subject);
        match outcome.status {
            Status::Pass => Truth::Yes,
            Status::Fail => Truth::No,
            _ => Truth::Unknown(outcome.reason.unwrap_or_else(|| format!("{} unknown", comparison.metric))),
        }
    }

    fn test(&self, test: &Test, rule: &Rule, subject: &Subject) -> Outcome {
        match test {
            Test::Measure { comparison, unit } => {
                self.compare(comparison, &Unit::parse(unit), tolerance_in(rule, unit), subject)
            }
            Test::Presence { metric, expected } => {
                self.compare(&equals(metric, Json::Bool(*expected)), &Unit::Boolean, None, subject)
            }
            Test::Answer { metric, prompt, pass, photo } => {
                let outcome = self.answer(metric, pass, subject);
                self.with_ask(outcome, metric, prompt, *photo, subject)
            }
            Test::Ratio { metric, basis, min_fraction, min_count, rounding } => {
                self.required_count(metric, basis, subject, |n| {
                    ratio_requirement(n, *min_fraction, *min_count, rounding)
                })
            }
            Test::Table { metric, basis, rows } => {
                self.required_count(metric, basis, subject, |n| table_requirement(n, rows))
            }
            Test::AllOf(tests) => combine_all(tests.iter().map(|t| self.test(t, rule, subject)).collect()),
            Test::AnyOf(tests) => combine_any(tests.iter().map(|t| self.test(t, rule, subject)).collect()),
            Test::Unsupported(json) => {
                Outcome::new(Status::NeedsInfo, String::new()).because(format!("unsupported test {json}"))
            }
        }
    }

    fn answer(&self, metric: &str, pass: &Answer, subject: &Subject) -> Outcome {
        let comparison = match pass {
            Answer::Equals(value) => equals(metric, value.clone()),
            Answer::Compare { op, value } => Comparison { metric: metric.to_string(), op: *op, value: value.clone() },
        };
        let unit = self.ctx.catalog.metric(metric).map(|m| m.unit()).unwrap_or(Unit::Text);
        self.compare(&comparison, &unit, None, subject)
    }

    /// Attach the question to ask when the answer itself is what is missing.
    fn with_ask(&self, mut outcome: Outcome, metric: &str, prompt: &str, photo: bool, subject: &Subject) -> Outcome {
        let unanswered = outcome.status == Status::NeedsInfo && outcome.measured.is_none();
        let Some(def) = self.ctx.catalog.metric(metric).filter(|_| unanswered) else {
            return outcome;
        };
        outcome.ask = Some(Ask {
            subject_id: self.metric_target(subject, metric).id.clone(),
            metric: metric.to_string(),
            prompt: prompt.to_string(),
            value_type: value_type_name(&def.value_type).to_string(),
            unit: def.raw_unit.clone(),
            options: def.enum_values.clone(),
            photo,
        });
        outcome
    }

    /// Compare a metric with the rule's limit in `unit`, widening the measurement by `tolerance`.
    fn compare(&self, comparison: &Comparison, unit: &Unit, tolerance: Option<f64>, subject: &Subject) -> Outcome {
        let measurement = match self.metric(subject, &comparison.metric) {
            Extraction::Measured(m) => m,
            Extraction::Unknown(reason) => return Outcome::new(Status::NeedsInfo, String::new()).because(reason),
            Extraction::NotApplicable(reason) => {
                return Outcome::new(Status::NotApplicable, String::new()).because(reason);
            }
        };
        let Some(measurement) = measurement.converted_to(unit) else {
            return Outcome::new(Status::NeedsInfo, String::new())
                .because(format!("{} is not in {unit}", comparison.metric));
        };
        let limit = match &comparison.value {
            Operand::Metric(other) => match self.metric(subject, other) {
                Extraction::Measured(m) => m.converted_to(unit).map(|m| value_json(&m.value)).unwrap_or(Json::Null),
                _ => return Outcome::new(Status::NeedsInfo, String::new()).because(format!("{other} unknown")),
            },
            Operand::Literal(json) => json.clone(),
        };
        let status = judge(&measurement.value, comparison.op, &limit, tolerance.unwrap_or(0.0));
        let required = describe_requirement(comparison.op, &limit, unit);
        let mut outcome = Outcome::new(status, required);
        outcome.reason = (status == Status::NeedsInfo).then(|| range_reason(&measurement, tolerance));
        outcome.measured = Some(measured_value(&measurement, comparison.op, unit));
        outcome.location = measurement.location;
        outcome.provenance = Some(provenance(&measurement));
        outcome
    }

    fn required_count(
        &self,
        metric: &str,
        basis: &str,
        subject: &Subject,
        requirement: impl Fn(f64) -> Option<f64>,
    ) -> Outcome {
        let basis_value = match self.metric(subject, basis) {
            Extraction::NotApplicable(reason) => {
                return Outcome::new(Status::NotApplicable, String::new()).because(reason);
            }
            other => match exact_number(&other) {
                Some(value) => value,
                None => return Outcome::new(Status::NeedsInfo, String::new()).because(format!("{basis} unknown")),
            },
        };
        match requirement(basis_value) {
            None => Outcome::new(Status::NotApplicable, String::new())
                .because(format!("{basis} is {}", format_number(basis_value))),
            Some(required) => self.compare(
                &Comparison { metric: metric.to_string(), op: Op::Ge, value: Operand::Literal(Json::from(required)) },
                &Unit::Count,
                None,
                subject,
            ),
        }
    }
}

fn yes_no(b: bool) -> Truth {
    if b { Truth::Yes } else { Truth::No }
}

fn all_truth(items: impl Iterator<Item = Truth>) -> Truth {
    let mut result = Truth::Yes;
    for item in items {
        match item {
            Truth::No => return Truth::No,
            Truth::Unknown(r) => result = Truth::Unknown(r),
            Truth::Yes => {}
        }
    }
    result
}

fn any_truth(items: impl Iterator<Item = Truth>) -> Truth {
    let mut result = Truth::No;
    for item in items {
        match item {
            Truth::Yes => return Truth::Yes,
            Truth::Unknown(r) => result = Truth::Unknown(r),
            Truth::No => {}
        }
    }
    result
}

fn equals(metric: &str, value: Json) -> Comparison {
    Comparison { metric: metric.to_string(), op: Op::Eq, value: Operand::Literal(value) }
}

fn tolerance_in(rule: &Rule, unit: &str) -> Option<f64> {
    let tolerance = rule.tolerance.as_ref()?;
    Unit::parse(&tolerance.unit).convert(tolerance.value, &Unit::parse(unit))
}

fn value_json(value: &Value) -> Json {
    match value {
        Value::Number { lo, hi } if lo == hi => Json::from(*lo),
        Value::Number { .. } => Json::Null,
        Value::Bool { value } => Json::Bool(*value),
        Value::Text { value } => Json::String(value.clone()),
    }
}

/// Pass when every value in the measured range (widened by the tolerance) passes, fail when every
/// value fails, needs_info otherwise.
pub(crate) fn judge(measured: &Value, op: Op, limit: &Json, tolerance: f64) -> Status {
    match measured {
        Value::Number { lo, hi } => judge_number(lo - tolerance, hi + tolerance, op, limit),
        Value::Bool { value } => judge_exact(&Json::Bool(*value), op, limit),
        Value::Text { value } => judge_exact(&Json::String(value.clone()), op, limit),
    }
}

fn decided(all_pass: bool, all_fail: bool) -> Status {
    match (all_pass, all_fail) {
        (true, _) => Status::Pass,
        (_, true) => Status::Fail,
        _ => Status::NeedsInfo,
    }
}

fn judge_number(lo: f64, hi: f64, op: Op, limit: &Json) -> Status {
    let single = limit.as_f64();
    let pair = limit.as_array().and_then(|a| Some((a.first()?.as_f64()?, a.get(1)?.as_f64()?)));
    match (op, single, pair) {
        (Op::Le, Some(v), _) => decided(hi <= v + 1e-9, lo > v + 1e-9),
        (Op::Lt, Some(v), _) => decided(hi < v - 1e-9, lo >= v - 1e-9),
        (Op::Ge, Some(v), _) => decided(lo >= v - 1e-9, hi < v - 1e-9),
        (Op::Gt, Some(v), _) => decided(lo > v + 1e-9, hi <= v + 1e-9),
        (Op::Eq, Some(v), _) => decided((lo - v).abs() < 1e-9 && (hi - v).abs() < 1e-9, v < lo - 1e-9 || v > hi + 1e-9),
        (Op::Ne, Some(v), _) => decided(v < lo - 1e-9 || v > hi + 1e-9, (lo - v).abs() < 1e-9 && (hi - v).abs() < 1e-9),
        (Op::Between, _, Some((a, b))) => decided(lo >= a - 1e-9 && hi <= b + 1e-9, hi < a - 1e-9 || lo > b + 1e-9),
        (Op::In, _, _) => judge_in_numbers(lo, hi, limit),
        (Op::Exists, _, _) => Status::Pass,
        _ => Status::NeedsInfo,
    }
}

fn judge_in_numbers(lo: f64, hi: f64, limit: &Json) -> Status {
    let options: Vec<f64> = limit.as_array().map(|a| a.iter().filter_map(Json::as_f64).collect()).unwrap_or_default();
    let exact = (hi - lo).abs() < 1e-9;
    decided(
        exact && options.iter().any(|v| (v - lo).abs() < 1e-9),
        !options.iter().any(|v| *v >= lo - 1e-9 && *v <= hi + 1e-9),
    )
}

fn judge_exact(measured: &Json, op: Op, limit: &Json) -> Status {
    let in_list = || limit.as_array().is_some_and(|a| a.contains(measured));
    match op {
        Op::Eq => decided(measured == limit, measured != limit),
        Op::Ne => decided(measured != limit, measured == limit),
        Op::In => decided(in_list(), !in_list()),
        Op::Exists => Status::Pass,
        _ => Status::NeedsInfo,
    }
}

fn ratio_requirement(basis: f64, fraction: f64, min_count: i64, rounding: &str) -> Option<f64> {
    if basis <= 0.0 {
        return None;
    }
    let raw = basis * fraction;
    let rounded = match rounding {
        "floor" => raw.floor(),
        "round" => raw.round(),
        _ => (raw - 1e-9).ceil(),
    };
    Some(rounded.max(min_count as f64).min(basis))
}

fn table_requirement(basis: f64, rows: &[TableRow]) -> Option<f64> {
    let n = basis.round() as i64;
    let row = rows.iter().find(|r| n >= r.min && r.max.is_none_or(|max| n <= max))?;
    if let Some(required) = row.required {
        return Some(required as f64);
    }
    if let Some(percent) = row.percent {
        return Some((n as f64 * percent / 100.0 - 1e-9).ceil());
    }
    let base = row.base.unwrap_or(0) as f64;
    let over = row.over.unwrap_or(0);
    let excess = (n - over).max(0) as f64;
    let per = row.per.map(|p| (excess / p as f64 - 1e-9).ceil()).unwrap_or(0.0);
    let percent_of_excess = row.percent_of_excess.map(|p| (excess * p / 100.0 - 1e-9).ceil()).unwrap_or(0.0);
    Some(base + per + percent_of_excess)
}

fn combine_all(outcomes: Vec<Outcome>) -> Outcome {
    let applicable: Vec<&Outcome> = outcomes.iter().filter(|o| o.status != Status::NotApplicable).collect();
    let required = join_required(&outcomes);
    let worst = applicable.iter().rev().max_by_key(|o| o.status.rank()).copied();
    match worst {
        None => outcomes.into_iter().next().unwrap_or_else(|| Outcome::new(Status::NotApplicable, String::new())),
        Some(o) => Outcome { required, ..o.clone() },
    }
}

fn combine_any(outcomes: Vec<Outcome>) -> Outcome {
    let required =
        outcomes.iter().map(|o| o.required.clone()).filter(|r| !r.is_empty()).collect::<Vec<_>>().join(" or ");
    let applicable: Vec<&Outcome> = outcomes.iter().filter(|o| o.status != Status::NotApplicable).collect();
    let pick = applicable
        .iter()
        .find(|o| o.status == Status::Pass)
        .or_else(|| applicable.iter().find(|o| o.status == Status::NeedsInfo))
        .or_else(|| applicable.first())
        .copied();
    match pick {
        None => outcomes.into_iter().next().unwrap_or_else(|| Outcome::new(Status::NotApplicable, String::new())),
        Some(o) => Outcome { required, ..o.clone() },
    }
}

fn join_required(outcomes: &[Outcome]) -> String {
    outcomes.iter().map(|o| o.required.clone()).filter(|r| !r.is_empty()).collect::<Vec<_>>().join(" and ")
}

fn describe_literal(limit: &Json) -> String {
    match limit {
        Json::Number(n) => format_number(n.as_f64().unwrap_or_default()),
        Json::Array(items) => items.iter().map(describe_literal).collect::<Vec<_>>().join(", "),
        Json::Bool(true) => "yes".into(),
        Json::Bool(false) => "no".into(),
        Json::String(s) => s.clone(),
        other => other.to_string(),
    }
}

fn describe_requirement(op: Op, limit: &Json, unit: &Unit) -> String {
    let suffix = match unit {
        Unit::Boolean | Unit::Text | Unit::Count | Unit::Ratio => String::new(),
        other => format!(" {other}"),
    };
    match (op, limit) {
        (Op::Eq, Json::Bool(_) | Json::String(_)) => describe_literal(limit),
        (Op::Between, _) => format!("between {}{suffix}", describe_literal(limit).replace(", ", " and ")),
        (Op::In, _) => format!("one of {}", describe_literal(limit)),
        _ => format!("{} {}{suffix}", op.symbol(), describe_literal(limit)),
    }
}

fn measured_value(m: &Measurement, op: Op, unit: &Unit) -> MeasuredValue {
    let (lo, hi) = match m.value {
        Value::Number { lo, hi } => (Some(lo), Some(hi)),
        _ => (None, None),
    };
    let nearest = match op {
        Op::Le | Op::Lt => hi,
        _ => lo,
    };
    MeasuredValue {
        text: m.value.describe(),
        value: nearest.filter(|v| v.is_finite()),
        lo,
        hi: hi.filter(|v| v.is_finite()),
        unit: unit.symbol(),
    }
}

fn range_reason(m: &Measurement, tolerance: Option<f64>) -> String {
    let base = if m.value.is_exact() {
        "within the measurement tolerance of the limit".to_string()
    } else {
        format!("measured range {} straddles the limit", m.value.describe())
    };
    let note = m.note.as_ref().map(|n| format!(" ({n})")).unwrap_or_default();
    let tolerance =
        tolerance.filter(|t| *t > 0.0).map(|t| format!("; tolerance {}", format_number(t))).unwrap_or_default();
    format!("{base}{note}{tolerance}")
}

fn provenance(m: &Measurement) -> String {
    match &m.provenance {
        Provenance::Geometry => "geometry".into(),
        Provenance::Observation { id, source } => format!("observation {id} ({source:?})").to_lowercase(),
    }
}

fn finding(rule: &Rule, subject: &Subject, outcome: Outcome) -> Finding {
    let message = message(rule, &outcome);
    let severity = severity(rule, &outcome);
    let evidence = match &outcome.provenance {
        Some(p) => format!("{}: {p}", rule.evidence),
        None => rule.evidence.clone(),
    };
    Finding {
        rule_id: rule.id.clone(),
        jurisdiction: rule.jurisdiction.clone(),
        section: rule.section.clone(),
        title: rule.title.clone(),
        subject_id: subject.id.clone(),
        room_id: subject.room_id.clone(),
        status: outcome.status,
        measured: outcome.measured,
        required: outcome.required,
        message,
        evidence,
        severity,
        location: outcome.location.or(subject.location),
        counterpart: rule.counterpart.clone(),
        ask: outcome.ask,
    }
}

fn value_type_name(value_type: &ValueType) -> &'static str {
    match value_type {
        ValueType::Number => "number",
        ValueType::Integer => "integer",
        ValueType::Boolean => "boolean",
        ValueType::Enum => "enum",
        ValueType::Other => "text",
    }
}

fn exact_number(extraction: &Extraction) -> Option<f64> {
    match extraction.measurement()?.value {
        Value::Number { lo, hi } if lo == hi => Some(lo),
        _ => None,
    }
}

fn severity(rule: &Rule, outcome: &Outcome) -> String {
    let unverified_level = outcome.status == Status::NeedsInfo
        && outcome.reason.as_deref().is_some_and(|r| r.contains(LEVEL_FLOOR_ASSUMED));
    if unverified_level { ADVISORY.to_string() } else { rule.severity.clone() }
}

fn message(rule: &Rule, outcome: &Outcome) -> String {
    let measured = outcome.measured.as_ref().map(|m| format!("{} {}", m.text, m.unit).trim().to_string());
    match (outcome.status, measured) {
        (Status::Pass, Some(m)) => format!("{}: measured {m}, meets {}.", rule.title, outcome.required),
        (Status::Pass, None) => format!("{}: meets the requirement.", rule.title),
        (Status::Fail, Some(m)) => format!("{}: measured {m}, required {}.", rule.title, outcome.required),
        (Status::Fail, None) => format!("{}: does not meet {}.", rule.title, outcome.required),
        (Status::NeedsInfo, _) => format!(
            "{}: needs more information ({}).",
            rule.title,
            outcome.reason.as_deref().unwrap_or("value unknown")
        ),
        (Status::NotApplicable, _) => {
            format!("{}: not applicable ({}).", rule.title, outcome.reason.as_deref().unwrap_or("out of scope"))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn ranges_decide_only_when_wholly_on_one_side() {
        assert_eq!(judge(&Value::exact(42.0), Op::Le, &json!(36), 0.0), Status::Fail);
        assert_eq!(judge(&Value::exact(34.0), Op::Le, &json!(36), 0.0), Status::Pass);
        assert_eq!(judge(&Value::range(35.0, 37.0), Op::Le, &json!(36), 0.0), Status::NeedsInfo);
        assert_eq!(judge(&Value::exact(35.8), Op::Le, &json!(36), 0.5), Status::NeedsInfo);
        assert_eq!(judge(&Value::range(33.5, 34.5), Op::Ge, &json!(32), 0.0), Status::Pass);
        assert_eq!(judge(&Value::range(30.0, f64::INFINITY), Op::Ge, &json!(48), 0.0), Status::NeedsInfo);
        assert_eq!(judge(&Value::exact(18.0), Op::Between, &json!([17, 19]), 0.0), Status::Pass);
        assert_eq!(judge(&Value::Bool { value: false }, Op::Eq, &json!(true), 0.0), Status::Fail);
        assert_eq!(judge(&Value::Text { value: "forward".into() }, Op::In, &json!(["forward"]), 0.0), Status::Pass);
    }

    #[test]
    fn parking_table_and_entrance_ratio() {
        let rows: Vec<TableRow> = serde_json::from_value(json!([
            {"min": 1, "max": 25, "required": 1}, {"min": 501, "max": 1000, "percent": 2},
            {"min": 1001, "max": null, "base": 20, "per": 100, "over": 1000}
        ]))
        .unwrap();
        assert_eq!(table_requirement(10.0, &rows), Some(1.0));
        assert_eq!(table_requirement(600.0, &rows), Some(12.0));
        assert_eq!(table_requirement(1250.0, &rows), Some(23.0));
        assert_eq!(ratio_requirement(3.0, 0.6, 1, "ceil"), Some(2.0));
        assert_eq!(ratio_requirement(0.0, 0.6, 1, "ceil"), None);
    }
}
