//! A room the scanner had to split (its scene-size limit) arrives as two rooms over the same floor.
//! Both are evaluated, so the same door or object would be reported twice; keep one finding per
//! element, the more severe one, so nothing that fails is hidden.

use crate::geometry::Bounds2;
use crate::rules::Finding;
use crate::scene::Scene;
use std::collections::{BTreeMap, HashMap};

/// Rooms whose plan bounds overlap by more than this share of the smaller one cover the same space.
const SAME_SPACE_OVERLAP: f64 = 0.5;
/// Two findings of one rule this close together describe the same element.
const SAME_ELEMENT_DISTANCE: f64 = 0.6;

pub fn drop_split_room_duplicates(findings: Vec<Finding>, scene: &Scene) -> Vec<Finding> {
    let footprints: HashMap<&str, (i32, Bounds2)> =
        scene.rooms.iter().map(|r| (r.id.as_str(), (r.storey, r.floor.bounds()))).collect();
    let same_space = |a: &str, b: &str| match (footprints.get(a), footprints.get(b)) {
        (Some((sa, ba)), Some((sb, bb))) => a != b && sa == sb && overlap_share(ba, bb) > SAME_SPACE_OVERLAP,
        _ => false,
    };
    let mut by_rule: BTreeMap<String, Vec<Finding>> = BTreeMap::new();
    for finding in findings {
        let kept = by_rule.entry(finding.rule_id.clone()).or_default();
        match kept.iter_mut().find(|k| is_same_element(k, &finding, &same_space)) {
            Some(existing) if finding.status.rank() > existing.status.rank() => *existing = finding,
            Some(_) => {}
            None => kept.push(finding),
        }
    }
    by_rule.into_values().flatten().collect()
}

fn is_same_element(a: &Finding, b: &Finding, same_space: &impl Fn(&str, &str) -> bool) -> bool {
    let (Some(room_a), Some(room_b)) = (a.room_id.as_deref(), b.room_id.as_deref()) else { return false };
    if !same_space(room_a, room_b) {
        return false;
    }
    let both_are_the_rooms = a.subject_id == room_a && b.subject_id == room_b;
    let close = matches!((a.location, b.location), (Some(p), Some(q)) if p.distance(q) < SAME_ELEMENT_DISTANCE);
    both_are_the_rooms || close
}

fn overlap_share(a: &Bounds2, b: &Bounds2) -> f64 {
    let width = (a.max.x.min(b.max.x) - a.min.x.max(b.min.x)).max(0.0);
    let depth = (a.max.y.min(b.max.y) - a.min.y.max(b.min.y)).max(0.0);
    let smaller = (a.width() * a.height()).min(b.width() * b.height());
    if smaller <= 0.0 { 0.0 } else { width * depth / smaller }
}
