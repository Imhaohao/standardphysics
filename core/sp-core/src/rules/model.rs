//! Rulepack data model (`rules/schema/rule.schema.json`), parsed defensively: an unknown test or
//! condition shape becomes `Unsupported` and evaluates to needs_info instead of failing the load.

use serde::Deserialize;
use serde_json::Value as Json;

pub const ADA: &str = "ADA2010";
pub const CBC: &str = "CBC11B";

#[derive(Debug, Clone)]
pub struct RulePack {
    pub version: String,
    pub jurisdiction: String,
    pub edition: String,
    pub rules: Vec<Rule>,
}

#[derive(Debug, Clone)]
pub struct Rule {
    pub id: String,
    pub jurisdiction: String,
    pub section: String,
    pub title: String,
    pub summary: String,
    pub applies_to: Vec<String>,
    pub scoping: Scoping,
    pub test: Test,
    pub evidence: String,
    pub tolerance: Option<Tolerance>,
    pub severity: String,
    pub source_url: String,
    pub counterpart: Option<String>,
    pub stricter_than: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WhenUnknown {
    NeedsInfo,
    NotApplicable,
    Apply,
}

#[derive(Debug, Clone)]
pub struct Scoping {
    pub text: String,
    pub when: Option<Condition>,
    pub when_unknown: WhenUnknown,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Tolerance {
    pub value: f64,
    pub unit: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Op {
    Le,
    Ge,
    Lt,
    Gt,
    Eq,
    Ne,
    Between,
    In,
    Exists,
}

impl Op {
    pub fn parse(raw: &str) -> Option<Op> {
        Some(match raw {
            "<=" => Op::Le,
            ">=" => Op::Ge,
            "<" => Op::Lt,
            ">" => Op::Gt,
            "==" | "=" => Op::Eq,
            "!=" => Op::Ne,
            "between" => Op::Between,
            "in" => Op::In,
            "exists" => Op::Exists,
            _ => return None,
        })
    }

    pub fn symbol(self) -> &'static str {
        match self {
            Op::Le => "<=",
            Op::Ge => ">=",
            Op::Lt => "<",
            Op::Gt => ">",
            Op::Eq => "==",
            Op::Ne => "!=",
            Op::Between => "between",
            Op::In => "in",
            Op::Exists => "exists",
        }
    }
}

/// The right-hand side of a comparison: a literal, a list (for between/in), or another metric.
#[derive(Debug, Clone, PartialEq)]
pub enum Operand {
    Literal(Json),
    Metric(String),
}

impl Operand {
    fn parse(json: &Json) -> Operand {
        match json.get("metric").and_then(Json::as_str) {
            Some(metric) if json.is_object() => Operand::Metric(metric.to_string()),
            _ => Operand::Literal(json.clone()),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Comparison {
    pub metric: String,
    pub op: Op,
    pub value: Operand,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Condition {
    Compare(Comparison),
    All(Vec<Condition>),
    Any(Vec<Condition>),
    Not(Box<Condition>),
    CategoryPresent(String),
    RoomKindIn(Vec<String>),
    SubjectCategoryIn(Vec<String>),
    Unsupported(Json),
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct TableRow {
    pub min: i64,
    pub max: Option<i64>,
    pub required: Option<i64>,
    pub percent: Option<f64>,
    pub base: Option<i64>,
    pub per: Option<i64>,
    pub over: Option<i64>,
    pub percent_of_excess: Option<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Test {
    Measure { comparison: Comparison, unit: String },
    Presence { metric: String, expected: bool },
    /// An owner answer (question) or photo label compared with the passing answer.
    Answer { metric: String, prompt: String, pass: Answer, photo: bool },
    Ratio { metric: String, basis: String, min_fraction: f64, min_count: i64, rounding: String },
    Table { metric: String, basis: String, rows: Vec<TableRow> },
    AllOf(Vec<Test>),
    AnyOf(Vec<Test>),
    Unsupported(Json),
}

#[derive(Debug, Clone, PartialEq)]
pub enum Answer {
    Equals(Json),
    Compare { op: Op, value: Operand },
}

#[derive(Debug, thiserror::Error)]
pub enum RuleLoadError {
    #[error("rulepack JSON did not parse: {0}")]
    Json(#[from] serde_json::Error),
    #[error("rulepack is missing `{0}`")]
    Missing(&'static str),
}

fn text(json: &Json, key: &str) -> String {
    json.get(key).and_then(Json::as_str).unwrap_or_default().to_string()
}

fn strings(json: &Json, key: &str) -> Vec<String> {
    json.get(key).and_then(Json::as_array).map(|a| a.iter().filter_map(Json::as_str).map(str::to_string).collect()).unwrap_or_default()
}

impl RulePack {
    pub fn from_json(source: &str) -> Result<RulePack, RuleLoadError> {
        let json: Json = serde_json::from_str(source)?;
        let rules = json.get("rules").and_then(Json::as_array).ok_or(RuleLoadError::Missing("rules"))?;
        let jurisdiction = text(&json, "jurisdiction");
        Ok(RulePack {
            version: text(&json, "version"),
            edition: text(&json, "edition"),
            rules: rules.iter().map(|r| Rule::parse(r, &jurisdiction)).collect(),
            jurisdiction,
        })
    }
}

impl Rule {
    fn parse(json: &Json, pack_jurisdiction: &str) -> Rule {
        let jurisdiction = Some(text(json, "jurisdiction")).filter(|j| !j.is_empty()).unwrap_or_else(|| pack_jurisdiction.to_string());
        Rule {
            id: text(json, "id"),
            jurisdiction,
            section: text(json, "section"),
            title: text(json, "title"),
            summary: text(json, "summary"),
            applies_to: strings(json, "applies_to"),
            scoping: parse_scoping(json.get("scoping")),
            test: json.get("test").map(parse_test).unwrap_or(Test::Unsupported(Json::Null)),
            evidence: text(json, "evidence"),
            tolerance: json.get("tolerance").and_then(|t| serde_json::from_value(t.clone()).ok()),
            severity: text(json, "severity"),
            source_url: text(json, "source_url"),
            counterpart: json.get("counterpart").and_then(Json::as_str).map(str::to_string),
            stricter_than: strings(json, "stricter_than"),
        }
    }

    /// Every metric the rule's scoping and test read.
    pub fn metrics(&self) -> Vec<&str> {
        let mut out = Vec::new();
        if let Some(when) = &self.scoping.when {
            when.collect_metrics(&mut out);
        }
        self.test.collect_metrics(&mut out);
        out
    }
}

fn parse_scoping(json: Option<&Json>) -> Scoping {
    let Some(json) = json else {
        return Scoping { text: String::new(), when: None, when_unknown: WhenUnknown::NeedsInfo };
    };
    if let Some(text) = json.as_str() {
        return Scoping { text: text.to_string(), when: None, when_unknown: WhenUnknown::NeedsInfo };
    }
    Scoping {
        text: text(json, "text"),
        when: json.get("when").filter(|w| !w.is_null()).map(parse_condition),
        when_unknown: json.get("when_unknown").and_then(|w| serde_json::from_value(w.clone()).ok()).unwrap_or(WhenUnknown::NeedsInfo),
    }
}

fn parse_comparison(json: &Json) -> Option<Comparison> {
    Some(Comparison {
        metric: json.get("metric")?.as_str()?.to_string(),
        op: Op::parse(json.get("op")?.as_str()?)?,
        value: json.get("value").map(Operand::parse).unwrap_or(Operand::Literal(Json::Null)),
    })
}

fn parse_conditions(json: &Json) -> Vec<Condition> {
    json.as_array().map(|items| items.iter().map(parse_condition).collect()).unwrap_or_default()
}

pub fn parse_condition(json: &Json) -> Condition {
    let field = |key: &str| json.get(key);
    if let Some(all) = field("all") {
        return Condition::All(parse_conditions(all));
    }
    if let Some(any) = field("any") {
        return Condition::Any(parse_conditions(any));
    }
    if let Some(not) = field("not") {
        return Condition::Not(Box::new(parse_condition(not)));
    }
    if let Some(category) = field("category_present").and_then(Json::as_str) {
        return Condition::CategoryPresent(category.to_string());
    }
    if field("room_kind_in").is_some() {
        return Condition::RoomKindIn(strings(json, "room_kind_in"));
    }
    if field("subject_category_in").is_some() {
        return Condition::SubjectCategoryIn(strings(json, "subject_category_in"));
    }
    parse_comparison(json).map(Condition::Compare).unwrap_or_else(|| Condition::Unsupported(json.clone()))
}

fn parse_answer(json: Option<&Json>) -> Answer {
    let json = json.cloned().unwrap_or(Json::Bool(true));
    let compare = json.get("op").and_then(Json::as_str).and_then(Op::parse);
    match compare {
        Some(op) => Answer::Compare { op, value: json.get("value").map(Operand::parse).unwrap_or(Operand::Literal(Json::Null)) },
        None => Answer::Equals(json),
    }
}

pub fn parse_test(json: &Json) -> Test {
    let Some((kind, body)) = json.as_object().and_then(|o| o.iter().next()) else {
        return Test::Unsupported(json.clone());
    };
    parse_test_body(kind, body).unwrap_or_else(|| Test::Unsupported(json.clone()))
}

fn parse_test_body(kind: &str, body: &Json) -> Option<Test> {
    let metric = || text(body, "metric");
    Some(match kind {
        "measure" => Test::Measure { comparison: parse_comparison(body)?, unit: text(body, "unit") },
        "presence" => Test::Presence { metric: metric(), expected: body.get("expected").and_then(Json::as_bool).unwrap_or(true) },
        "question" => Test::Answer { metric: metric(), prompt: text(body, "prompt"), pass: parse_answer(body.get("pass_answer")), photo: false },
        "photo" => Test::Answer { metric: metric(), prompt: text(body, "prompt"), pass: parse_answer(body.get("expected")), photo: true },
        "ratio" => Test::Ratio {
            metric: metric(),
            basis: text(body, "basis_metric"),
            min_fraction: body.get("min_fraction").and_then(Json::as_f64).unwrap_or(1.0),
            min_count: body.get("min_count").and_then(Json::as_i64).unwrap_or(0),
            rounding: text(body, "rounding"),
        },
        "table" => Test::Table { metric: metric(), basis: text(body, "basis_metric"), rows: serde_json::from_value(body.get("rows")?.clone()).ok()? },
        "all_of" => Test::AllOf(body.as_array()?.iter().map(parse_test).collect()),
        "any_of" => Test::AnyOf(body.as_array()?.iter().map(parse_test).collect()),
        _ => return None,
    })
}

impl Condition {
    fn collect_metrics<'a>(&'a self, out: &mut Vec<&'a str>) {
        match self {
            Condition::Compare(c) => c.collect_metrics(out),
            Condition::All(items) | Condition::Any(items) => items.iter().for_each(|c| c.collect_metrics(out)),
            Condition::Not(inner) => inner.collect_metrics(out),
            _ => {}
        }
    }
}

impl Comparison {
    fn collect_metrics<'a>(&'a self, out: &mut Vec<&'a str>) {
        out.push(&self.metric);
        if let Operand::Metric(m) = &self.value {
            out.push(m);
        }
    }
}

impl Test {
    fn collect_metrics<'a>(&'a self, out: &mut Vec<&'a str>) {
        match self {
            Test::Measure { comparison, .. } => comparison.collect_metrics(out),
            Test::Presence { metric, .. } => out.push(metric),
            Test::Answer { metric, pass, .. } => {
                out.push(metric);
                if let Answer::Compare { value: Operand::Metric(m), .. } = pass {
                    out.push(m);
                }
            }
            Test::Ratio { metric, basis, .. } | Test::Table { metric, basis, .. } => out.extend([metric.as_str(), basis.as_str()]),
            Test::AllOf(tests) | Test::AnyOf(tests) => tests.iter().for_each(|t| t.collect_metrics(out)),
            Test::Unsupported(_) => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_measure_with_scoping_and_tolerance() {
        let json = r#"{"jurisdiction":"ADA2010","rules":[{"id":"ADA-904.4.1","section":"904.4.1","title":"Counter height",
          "summary":"Low counter","applies_to":["counter"],
          "scoping":{"text":"t","when":{"all":[{"metric":"site.facility_type","op":"in","value":["retail"]},{"not":{"category_present":"bar_counter"}}]},"when_unknown":"apply"},
          "test":{"measure":{"metric":"counter.top_height","op":"<=","value":36,"unit":"in"}},
          "evidence":"measured","tolerance":{"value":0.5,"unit":"in","policy":"needs_info_within"},"severity":"violation",
          "source_url":"https://x","counterpart":"CBC-11B-904.4.1","stricter_than":[]}]}"#;
        let pack = RulePack::from_json(json).unwrap();
        let rule = &pack.rules[0];
        assert!(matches!(rule.test, Test::Measure { ref comparison, .. } if comparison.op == Op::Le));
        assert!(matches!(rule.scoping.when, Some(Condition::All(ref c)) if c.len() == 2));
        assert_eq!(rule.scoping.when_unknown, WhenUnknown::Apply);
        assert_eq!(rule.tolerance.as_ref().unwrap().value, 0.5);
        assert_eq!(rule.metrics(), vec!["site.facility_type", "counter.top_height"]);
    }

    #[test]
    fn unknown_test_shapes_are_kept_as_unsupported() {
        assert!(matches!(parse_test(&serde_json::json!({"telepathy": {}})), Test::Unsupported(_)));
        assert!(matches!(parse_condition(&serde_json::json!({"weird": 1})), Condition::Unsupported(_)));
    }
}
