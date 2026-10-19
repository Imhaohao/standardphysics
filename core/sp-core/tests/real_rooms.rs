mod common;

use common::{fixture, repo_engine};
use sp_core::rules::{Finding, Status};
use sp_core::scene::{OpeningKind, Room, Scene};
use sp_core::units::to_inches;
use sp_core::roomplan::{import_captured_json, merge_rooms};
use std::time::Instant;

const FIXTURES: [&str; 2] = ["apple_bedroom3.room.json", "apple_livingroom.room.json"];

fn import(name: &str) -> Vec<Room> {
    import_captured_json(&fixture(name)).expect("fixture imports")
}

fn real_scene() -> Scene {
    merge_rooms(FIXTURES.iter().flat_map(|name| import(name)).collect())
}

#[test]
fn fixtures_import_with_plausible_geometry() {
    for name in FIXTURES {
        for room in import(name) {
            assert!(room.walls.len() >= 3, "{name}: {} walls", room.walls.len());
            let area = room.floor.area();
            assert!((4.0..200.0).contains(&area), "{name}: floor area {area}");
            assert!(room.walls.iter().all(|w| (2.0..4.0).contains(&w.height)), "{name}: wall heights");
        }
    }
}

#[test]
fn fixture_doors_keep_their_captured_widths() {
    let mut widths: Vec<f64> = FIXTURES
        .iter()
        .flat_map(|n| import(n))
        .flat_map(|r| r.openings)
        .filter(|o| o.kind == OpeningKind::Door)
        .map(|o| to_inches(o.width))
        .collect();
    widths.sort_by(f64::total_cmp);
    let expected = [29.0, 29.9, 144.4];
    assert_eq!(widths.len(), expected.len());
    for (width, expected) in widths.iter().zip(expected) {
        assert!((width - expected).abs() < 0.1, "door width {width} in, expected {expected}");
    }
}

fn assert_sane(findings: &[Finding]) {
    assert!(!findings.is_empty());
    assert!(findings.iter().any(|f| f.status == Status::Pass));
    assert!(findings.iter().any(|f| f.status == Status::NeedsInfo));
    for f in findings.iter().filter(|f| f.status == Status::Fail) {
        assert!(f.measured.is_some() || !f.message.is_empty(), "{} on {} fails without evidence", f.rule_id, f.subject_id);
    }
}

#[test]
fn real_scene_evaluates_quickly_and_sanely() {
    let Some(mut engine) = repo_engine() else { return };
    let started = Instant::now();
    engine.set_scene(real_scene());
    let report = engine.evaluate_all();
    let elapsed = started.elapsed();
    assert_eq!(report.jurisdictions.len(), 2);
    assert_sane(&engine.findings());
    assert!(!report.governing.is_empty());
    assert!(elapsed.as_secs_f64() < 5.0, "evaluation took {elapsed:?}");
}

#[test]
fn update_room_matches_full_evaluation() {
    let Some(mut engine) = repo_engine() else { return };
    let scene = real_scene();
    let first = scene.rooms[0].clone();
    engine.set_scene(scene);
    let full = engine.evaluate_all().governing_counts;
    engine.update_room(first);
    assert_eq!(engine.report().governing_counts, full);
}

#[test]
fn every_finding_names_a_known_rule_and_subject() {
    let Some(mut engine) = repo_engine() else { return };
    engine.set_scene(real_scene());
    engine.evaluate_all();
    let rule_ids: std::collections::HashSet<_> =
        engine.rulepacks().iter().flat_map(|p| p.rules.iter().map(|r| r.id.clone())).collect();
    for f in engine.findings() {
        assert!(rule_ids.contains(&f.rule_id), "unknown rule {}", f.rule_id);
        assert!(!f.subject_id.is_empty());
    }
}
