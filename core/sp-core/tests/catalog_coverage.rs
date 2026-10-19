//! Every metric in rules/metrics.json has an extractor or comes from observations, and every rule
//! uses only catalog metrics and supported test shapes.

mod common;

use sp_core::metrics::{MetricSource, metric_source, registered_metric_ids};
use sp_core::rules::{Answer, Condition, Operand, Test};

#[test]
fn every_catalog_metric_has_an_extractor_or_observation_source() {
    let Some(engine) = common::repo_engine() else { return };
    let catalog = engine.catalog();
    let missing: Vec<&str> = catalog.metrics.iter().filter(|m| metric_source(m) == MetricSource::Missing).map(|m| m.id.as_str()).collect();
    assert!(missing.is_empty(), "measured metrics without an extractor: {missing:?}");
    let extractors = catalog.metrics.iter().filter(|m| metric_source(m) == MetricSource::Extractor).count();
    let observations = catalog.metrics.len() - extractors;
    eprintln!("{} metrics: {extractors} with extractors, {observations} from observations only", catalog.metrics.len());
}

#[test]
fn every_extractor_names_a_catalog_metric() {
    let Some(engine) = common::repo_engine() else { return };
    let stale: Vec<&str> = registered_metric_ids().into_iter().filter(|id| engine.catalog().metric(id).is_none()).collect();
    assert!(stale.is_empty(), "extractors for metrics not in the catalog: {stale:?}");
}

#[test]
fn every_rule_references_known_metrics() {
    let Some(engine) = common::repo_engine() else { return };
    let unknown: Vec<String> = engine
        .rulepacks()
        .iter()
        .flat_map(|p| &p.rules)
        .flat_map(|r| r.metrics().into_iter().filter(|m| engine.catalog().metric(m).is_none()).map(move |m| format!("{} -> {m}", r.id)))
        .collect();
    assert!(unknown.is_empty(), "rules reference unknown metrics: {unknown:?}");
}

#[test]
fn every_rule_applies_to_a_known_element_or_category() {
    let Some(engine) = common::repo_engine() else { return };
    let catalog = engine.catalog();
    let known = |t: &str| catalog.elements.iter().any(|e| e.id == t) || catalog.is_known_category(t) || catalog.object_categories.iter().any(|c| c.canonical.as_deref() == Some(t));
    let unknown: Vec<String> =
        engine.rulepacks().iter().flat_map(|p| &p.rules).flat_map(|r| r.applies_to.iter().filter(|t| !known(t)).map(move |t| format!("{} -> {t}", r.id))).collect();
    assert!(unknown.is_empty(), "unknown applies_to: {unknown:?}");
}

fn test_supported(test: &Test) -> bool {
    match test {
        Test::Unsupported(_) => false,
        Test::AllOf(tests) | Test::AnyOf(tests) => tests.iter().all(test_supported),
        Test::Answer { pass: Answer::Compare { value: Operand::Literal(_) | Operand::Metric(_), .. }, .. } => true,
        _ => true,
    }
}

fn condition_supported(condition: &Condition) -> bool {
    match condition {
        Condition::Unsupported(_) => false,
        Condition::All(items) | Condition::Any(items) => items.iter().all(condition_supported),
        Condition::Not(inner) => condition_supported(inner),
        _ => true,
    }
}

#[test]
fn every_rule_test_and_condition_is_understood() {
    let Some(engine) = common::repo_engine() else { return };
    let rules: Vec<_> = engine.rulepacks().iter().flat_map(|p| &p.rules).collect();
    let bad: Vec<&str> = rules
        .iter()
        .filter(|r| !test_supported(&r.test) || r.scoping.when.as_ref().is_some_and(|c| !condition_supported(c)))
        .map(|r| r.id.as_str())
        .collect();
    assert!(bad.is_empty(), "rules with unsupported shapes: {bad:?}");
    assert!(rules.len() > 400, "expected both rulepacks, got {} rules", rules.len());
}
