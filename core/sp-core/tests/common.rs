#![allow(dead_code)]

use sp_core::Engine;
use std::path::PathBuf;

pub fn repo_path(relative: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").join(relative)
}

pub fn read(relative: &str) -> Option<String> {
    std::fs::read_to_string(repo_path(relative)).ok()
}

pub fn fixture(name: &str) -> String {
    read(&format!("packages/fixtures/standardphysics_fixtures/data/real/{name}")).expect("fixture present")
}

/// The engine over the repo's rules, or `None` (with a message) while rules/ is not written yet.
pub fn repo_engine() -> Option<Engine> {
    let (Some(catalog), Some(ada), Some(cbc)) = (read("rules/metrics.json"), read("rules/ada2010.json"), read("rules/cbc11b.json")) else {
        eprintln!("rules/metrics.json or a rulepack is missing; skipping");
        return None;
    };
    Some(Engine::new(&catalog, &[&ada, &cbc]).expect("repo rules load"))
}
