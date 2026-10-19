//! Doors, doorways and their maneuvering clearances (404).

use super::support::{needs_detail, needs_mesh, objects_of, vertical_extent, within_box_height, wrong_subject};
use crate::analysis::{StoreyAnalysis, estimated_clear_width};
use crate::geometry::{OrientedBox2, Vec2};
use crate::grid::{DoorGap, Probe, door_gap};
use crate::metrics::subject::Subject;
use crate::metrics::{EvalContext, Extraction, Extractor};
use crate::scene::{Opening, OpeningKind, Room};
use crate::units::inches;

pub const EXTRACTORS: &[(&str, Extractor)] = &[
    ("door.clear_width", clear_width),
    ("door.opening_depth", opening_depth),
    ("door.approach_pull_side", approach),
    ("door.approach_push_side", approach),
    ("door.maneuvering_clearance_pull_side_depth", pull_side_depth),
    ("door.maneuvering_clearance_pull_side_latch_extension", pull_side_latch_extension),
    ("door.maneuvering_clearance_pull_side_hinge_extension", pull_side_hinge_extension),
    ("door.maneuvering_clearance_push_side_depth", push_side_depth),
    ("door.maneuvering_clearance_push_side_latch_extension", push_side_latch_extension),
    ("door.maneuvering_clearance_push_side_hinge_extension", push_side_latch_extension),
    ("door.maneuvering_clearance_slope", needs_mesh),
    ("door.pull_side_is_exterior", pull_side_is_exterior),
    ("door.recess_depth", recess_depth),
    ("doorway.maneuvering_depth", doorway_maneuvering_depth),
    ("door.maneuvering_clearance_width_doorway", doorway_maneuvering_width),
    ("door.hardware_height", hardware_height),
    ("door.is_exterior", is_exterior),
    ("door.vision_lite_bottom_height", needs_detail),
    ("door.series_distance", series_distance),
    ("door.series_swing_direction", series_swing_direction),
    ("door.swings_into_fixture_clear_floor", swings_into_fixture_clear_floor),
    ("door.swings_into_route_reduces_width", swings_into_route),
    ("door.has_closer", has_closer),
    ("door_closer.height", closer_height),
    ("threshold.height", threshold_height),
];

/// Uncertainty in a door's clear width from frame width alone: leaf plus stop take 1.5 to 2.5 in.
const CLEAR_WIDTH_ALLOWANCE_RANGE: (f64, f64) = (0.0381, 0.0635);
/// Unknown wall thickness when only one side is scanned: 4 to 12 in.
const WALL_THICKNESS_RANGE: (f64, f64) = (0.1016, 0.3048);
const DEPTH_PROBE: f64 = 2.0;
const EXTENSION_PROBE: f64 = 1.0;
const NEAR_DOOR: f64 = 0.6;

type Range = (f64, f64);

struct DoorSite<'a> {
    room: &'a Room,
    opening: &'a Opening,
    gap: DoorGap,
    analysis: &'a StoreyAnalysis,
}

fn door_site<'a>(ctx: &EvalContext<'a>, subject: &Subject) -> Result<DoorSite<'a>, Extraction> {
    let (Some(room), Some(opening)) = (ctx.room(subject), ctx.opening(subject)) else { return Err(wrong_subject()) };
    if !opening.kind.is_passable() {
        return Err(wrong_subject());
    }
    let analysis = ctx.analysis(room.storey).ok_or_else(|| Extraction::unknown("storey not analysed"))?;
    Ok(DoorSite { room, opening, gap: door_gap(room, opening), analysis })
}

fn leaf_door<'a>(ctx: &EvalContext<'a>, subject: &Subject) -> Result<DoorSite<'a>, Extraction> {
    if subject.has_tag("toilet_compartment") {
        return Err(needs_detail(ctx, subject));
    }
    let site = door_site(ctx, subject)?;
    if site.opening.kind != OpeningKind::Door {
        return Err(Extraction::not_applicable("doorway without a door leaf"));
    }
    Ok(site)
}

fn range(r: Range) -> Extraction {
    Extraction::metres_range(r.0, r.1)
}

fn hull(ranges: impl IntoIterator<Item = Range>) -> Range {
    ranges.into_iter().fold((f64::INFINITY, f64::NEG_INFINITY), |(lo, hi), (a, b)| (lo.min(a), hi.max(b)))
}

fn clear_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if subject.has_tag("toilet_compartment") {
        return needs_detail(ctx, subject);
    }
    let Some(opening) = ctx.opening(subject).filter(|o| o.kind.is_passable()) else { return wrong_subject() };
    let estimate = estimated_clear_width(opening, 0.0);
    let measured = match opening.kind {
        OpeningKind::Door => range((estimate - CLEAR_WIDTH_ALLOWANCE_RANGE.1, estimate - CLEAR_WIDTH_ALLOWANCE_RANGE.0)),
        _ => Extraction::metres(estimate),
    };
    measured.located(Some(opening.center)).noted("frame width less an allowance for the leaf and stop")
}

/// Wall thickness at the opening: the gap between this room's wall and the connected room's
/// parallel wall when both sides were scanned, otherwise a typical range.
fn opening_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let site = match door_site(ctx, subject) {
        Ok(site) => site,
        Err(e) => return e,
    };
    match facing_wall_gap(ctx, &site) {
        Some(depth) => Extraction::metres(depth),
        None => range(WALL_THICKNESS_RANGE).noted("one side of the wall scanned; thickness assumed 4-12 in"),
    }
}

fn facing_wall_gap(ctx: &EvalContext, site: &DoorSite) -> Option<f64> {
    let neighbours = ctx.scene.connections.iter().filter(|c| c.opening_id.as_deref() == Some(site.opening.id.as_str()));
    let other_rooms = neighbours.filter_map(|c| ctx.scene.room(if c.from_room == site.room.id { &c.to_room } else { &c.from_room }));
    other_rooms
        .flat_map(|r| r.walls.iter())
        .filter(|w| w.segment().direction().dot(site.gap.along).abs() > 0.95)
        .map(|w| w.segment().distance_to(site.gap.center))
        .filter(|d| *d < 0.6)
        .reduce(f64::min)
}

/// A route crossing the door square-on approaches it from the front on both sides, whichever
/// way it swings; a side approach needs the hinge side, which the scan does not capture.
fn approach(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let site = match door_site(ctx, subject) {
        Ok(site) => site,
        Err(e) => return e,
    };
    let Some(heading) = arrival_heading(&site) else { return Extraction::unknown("no route reaches this door") };
    if heading.dot(site.gap.normal).abs() >= std::f64::consts::FRAC_1_SQRT_2 {
        Extraction::text("front")
    } else {
        Extraction::unknown("route arrives from the side and the hinge side is unknown")
    }
}

/// Direction of travel over the last (or, from an entrance, first) half metre of a route at the door.
fn arrival_heading(site: &DoorSite) -> Option<Vec2> {
    let id = &site.opening.id;
    if let Some(leg) = site.analysis.route_to(id).and_then(|r| r.leg.as_ref()) {
        let end = *leg.points.last()?;
        let before = leg.points.iter().rev().find(|p| p.distance(end) >= 0.5)?;
        return Some((end - *before).normalized());
    }
    let leaving = site.analysis.routes.iter().filter(|r| r.entrance.as_deref() == Some(id.as_str())).find_map(|r| r.leg.as_ref())?;
    let start = *leaving.points.first()?;
    let after = leaving.points.iter().find(|p| p.distance(start) >= 0.5)?;
    Some((*after - start).normalized())
}

struct Side {
    depth: Range,
    extensions: [Range; 2],
}

fn wall_face_offset(site: &DoorSite) -> f64 {
    let cell = site.analysis.grid.spec.cell;
    (site.gap.wall_thickness / 2.0).max(0.75 * cell) + cell
}

fn measure_side(site: &DoorSite, side: f64) -> Side {
    let grid = &site.analysis.grid;
    let normal = site.gap.normal * side;
    let face = wall_face_offset(site);
    let depth = Probe::new(site.gap.center + normal * face, normal, site.gap.width / 2.0).sweep(grid, DEPTH_PROBE);
    let depth = (depth.length, depth.upper_bound());
    let extension = |dir: f64| extension(site, normal, face, depth, dir);
    Side { depth, extensions: [extension(1.0), extension(-1.0)] }
}

/// Free floor beyond one edge of the door, along the wall, in a band up to 48 in deep.
fn extension(site: &DoorSite, normal: Vec2, face: f64, depth: Range, dir: f64) -> Range {
    let band = depth.0.min(inches(48.0));
    if band < 0.05 {
        return (0.0, if depth.1.is_infinite() { f64::INFINITY } else { 0.0 });
    }
    let along = site.gap.along * dir;
    let origin = site.gap.center + along * (site.gap.width / 2.0) + normal * (face + band / 2.0);
    let extent = Probe::new(origin, along, band / 2.0 - 0.01).sweep(&site.analysis.grid, EXTENSION_PROBE);
    (extent.length, extent.upper_bound())
}

/// The side a door swings into is its pull side; `None` when the swing was not captured.
fn pull_side(site: &DoorSite) -> Option<f64> {
    let swing = site.opening.swing.as_ref()?;
    let room_side = if site.room.floor.contains(site.gap.center + site.gap.normal * 0.3) { 1.0 } else { -1.0 };
    Some(if swing.swings_in { room_side } else { -room_side })
}

/// (pull side, push side) candidates: one each when the swing is known, both sides otherwise.
fn sides(site: &DoorSite) -> (Vec<Side>, Vec<Side>) {
    match pull_side(site) {
        Some(pull) => (vec![measure_side(site, pull)], vec![measure_side(site, -pull)]),
        None => {
            let both = || vec![measure_side(site, 1.0), measure_side(site, -1.0)];
            (both(), both())
        }
    }
}

fn side_metric(ctx: &EvalContext, subject: &Subject, pull: bool, read: fn(&Side) -> Vec<Range>) -> Extraction {
    let site = match leaf_door(ctx, subject) {
        Ok(site) => site,
        Err(e) => return e,
    };
    let (pull_sides, push_sides) = sides(&site);
    let chosen = if pull { pull_sides } else { push_sides };
    range(hull(chosen.iter().flat_map(read))).located(Some(site.opening.center))
}

fn pull_side_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    side_metric(ctx, subject, true, |s| vec![s.depth])
}

fn pull_side_latch_extension(ctx: &EvalContext, subject: &Subject) -> Extraction {
    side_metric(ctx, subject, true, |s| s.extensions.to_vec())
}

fn pull_side_hinge_extension(ctx: &EvalContext, subject: &Subject) -> Extraction {
    side_metric(ctx, subject, true, |s| s.extensions.to_vec())
}

fn push_side_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    side_metric(ctx, subject, false, |s| vec![s.depth])
}

fn push_side_latch_extension(ctx: &EvalContext, subject: &Subject) -> Extraction {
    side_metric(ctx, subject, false, |s| s.extensions.to_vec())
}

/// Only doorways deeper than 24 in need a maneuvering width (404.2.4.2).
fn doorway_maneuvering_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let site = match door_site(ctx, subject) {
        Ok(site) if site.opening.kind == OpeningKind::Opening => site,
        Ok(_) => return Extraction::not_applicable("door with a leaf"),
        Err(e) => return e,
    };
    let depth = facing_wall_gap(ctx, &site).unwrap_or(WALL_THICKNESS_RANGE.1);
    if depth <= inches(24.0) {
        return Extraction::not_applicable("doorway is not deeper than 24 in");
    }
    Extraction::metres(site.opening.width)
}

fn hardware_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if let Some(object) = ctx.object(subject) {
        return within_box_height(object);
    }
    nearby_part(ctx, subject, &["door_hardware"]).unwrap_or_else(|e| e)
}

fn nearby_part(ctx: &EvalContext, subject: &Subject, categories: &'static [&'static str]) -> Result<Extraction, Extraction> {
    let site = door_site(ctx, subject)?;
    let part = objects_of(site.room, categories).find(|o| o.center.plan().distance(site.gap.center) <= site.gap.width / 2.0 + NEAR_DOOR);
    part.map(within_box_height).ok_or_else(|| needs_detail(ctx, subject))
}

fn is_exterior(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let Some(opening) = ctx.opening(subject) else { return wrong_subject() };
    if ctx.scene.is_interior_opening(&opening.id) {
        Extraction::boolean(false)
    } else {
        Extraction::unknown("the far side was not scanned; the owner confirms whether it is outside")
    }
}

/// Another door within 3 m whose wall is parallel and offset: a vestibule or doors in series.
fn series_partner<'a>(ctx: &EvalContext<'a>, site: &DoorSite) -> Option<(DoorGap, &'a Opening, f64)> {
    let candidates = ctx.scene.rooms_on(site.room.storey).flat_map(|r| r.openings.iter().map(move |o| (r, o)));
    candidates
        .filter(|(_, o)| o.kind == OpeningKind::Door && o.id != site.opening.id)
        .map(|(r, o)| (door_gap(r, o), o))
        .filter(|(gap, _)| gap.normal.dot(site.gap.normal).abs() > 0.9)
        .map(|(gap, o)| {
            let offset = gap.center - site.gap.center;
            (gap, o, offset.dot(site.gap.normal).abs(), offset.dot(site.gap.along).abs())
        })
        .filter(|(_, _, across, lateral)| *across > 0.3 && *across < 3.0 && *lateral < 1.5)
        .min_by(|a, b| a.2.total_cmp(&b.2))
        .map(|(gap, o, across, _)| (gap, o, across))
}

fn series_distance(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let site = match leaf_door(ctx, subject) {
        Ok(site) => site,
        Err(e) => return e,
    };
    let Some((partner, other, across)) = series_partner(ctx, &site) else {
        return Extraction::not_applicable("no door in series");
    };
    let clear = across - (site.gap.wall_thickness + partner.wall_thickness) / 2.0;
    let both_swings_known = site.opening.swing.is_some() && other.swing.is_some();
    let worst = clear - site.opening.width - other.width;
    let measured = if both_swings_known { (clear - swing_into(&site, other), clear - swing_into(&site, other)) } else { (worst, clear) };
    range(measured).located(Some(site.opening.center))
}

/// Width of leaves that swing into the space between the two doors (assumes leaves swing away
/// from the room that owns each door when `swings_in` is false).
fn swing_into(site: &DoorSite, other: &Opening) -> f64 {
    let own = site.opening.swing.as_ref().is_some_and(|s| !s.swings_in) as u8 as f64 * site.opening.width;
    let theirs = other.swing.as_ref().is_some_and(|s| !s.swings_in) as u8 as f64 * other.width;
    own + theirs
}

fn series_swing_direction(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let site = match leaf_door(ctx, subject) {
        Ok(site) => site,
        Err(e) => return e,
    };
    match series_partner(ctx, &site) {
        None => Extraction::text("none"),
        Some((_, other, _)) => match (&site.opening.swing, &other.swing) {
            (Some(a), Some(b)) if a.swings_in == b.swings_in => Extraction::text("same"),
            (Some(a), Some(_)) if a.swings_in => Extraction::text("toward"),
            (Some(_), Some(_)) => Extraction::text("away"),
            _ => Extraction::unknown("door swing directions were not captured"),
        },
    }
}

/// The square a leaf sweeps on one side of its wall.
fn swing_zone(site: &DoorSite, side: f64) -> OrientedBox2 {
    let centre = site.gap.center + site.gap.normal * (side * (site.gap.wall_thickness / 2.0 + site.gap.width / 2.0));
    let yaw = (-site.gap.along.y).atan2(site.gap.along.x);
    OrientedBox2::new(centre, site.gap.width, site.gap.width, yaw)
}

fn room_side(site: &DoorSite) -> f64 {
    if site.room.floor.contains(site.gap.center + site.gap.normal * 0.3) { 1.0 } else { -1.0 }
}

fn swings_into_fixture_clear_floor(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let site = match leaf_door(ctx, subject) {
        Ok(site) => site,
        Err(e) => return e,
    };
    if site.opening.swing.as_ref().is_some_and(|s| !s.swings_in) {
        return Extraction::boolean(false);
    }
    let zone = swing_zone(&site, room_side(&site));
    let fixtures = site.room.objects.iter().filter(|o| super::clear_floor::needs_clear_floor(ctx, o));
    let overlaps = fixtures.filter_map(|o| super::clear_floor::clear_floor_area(ctx, site.room, o)).any(|area| area.overlaps(&zone));
    match (overlaps, site.opening.swing.is_some()) {
        (false, _) => Extraction::boolean(false),
        (true, true) => Extraction::boolean(true),
        (true, false) => Extraction::unknown("overlaps a fixture's clear floor if the door swings in; swing not captured"),
    }
}

/// A leaf open at 90 degrees stands `width` into the space it swings into; the route there still
/// needs 36 in beside it.
fn swings_into_route(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let site = match leaf_door(ctx, subject) {
        Ok(site) => site,
        Err(e) => return e,
    };
    let needed = site.gap.width + inches(36.0);
    let reduces = |side: f64| {
        let along = Probe::new(site.gap.center + site.gap.normal * side * wall_face_offset(&site), site.gap.normal * side, 0.05);
        along.sweep(&site.analysis.grid, needed).upper_bound() < needed
    };
    match pull_side(&site) {
        Some(side) => Extraction::boolean(reduces(side)),
        None => match (reduces(1.0), reduces(-1.0)) {
            (a, b) if a == b => Extraction::boolean(a),
            _ => Extraction::unknown("depends on which way the door swings, which was not captured"),
        },
    }
}

fn has_closer(ctx: &EvalContext, subject: &Subject) -> Extraction {
    match nearby_part(ctx, subject, &["door_closer"]) {
        Ok(_) => Extraction::boolean(true),
        Err(e) => e,
    }
}

fn closer_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if let Some(object) = ctx.object(subject) {
        return Extraction::metres(vertical_extent(object).0).located(Some(object.center));
    }
    nearby_part(ctx, subject, &["door_closer"])
        .map(|e| match e {
            Extraction::Measured(m) => match m.value {
                crate::metrics::Value::Number { lo, .. } => Extraction::metres(lo),
                _ => Extraction::Measured(m),
            },
            other => other,
        })
        .unwrap_or_else(|e| e)
}

fn threshold_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if let Some(object) = ctx.object(subject) {
        return Extraction::metres(object.size.y).located(Some(object.center));
    }
    let site = match door_site(ctx, subject) {
        Ok(site) => site,
        Err(e) => return e,
    };
    let threshold = objects_of(site.room, &["threshold"]).find(|o| o.center.plan().distance(site.gap.center) < site.gap.width);
    match threshold {
        Some(t) => Extraction::metres(t.size.y).located(Some(t.center)),
        None => needs_mesh(ctx, subject),
    }
}

fn pull_side_is_exterior(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if subject.has_tag("toilet_compartment") {
        return Extraction::boolean(false);
    }
    is_exterior(ctx, subject)
}

/// How far a wall or object beside the door (within 18 in of either edge) stands out past the
/// wall face; the latch edge is unknown, so the range covers both edges and both sides.
fn recess_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let site = match leaf_door(ctx, subject) {
        Ok(site) => site,
        Err(e) => return e,
    };
    let face = wall_face_offset(&site);
    let depths = [1.0, -1.0].into_iter().flat_map(|side| [1.0, -1.0].map(|edge| (side, edge))).map(|(side, edge)| {
        let beside = site.gap.center + site.gap.along * (edge * (site.gap.width / 2.0 + inches(9.0)));
        let normal = site.gap.normal * side;
        let probe = Probe::new(beside + normal * face, normal, inches(9.0) - 0.01);
        blocked_run(&site, probe)
    });
    range(hull(depths.map(|d| (d, d)))).located(Some(site.opening.center))
}

/// Distance the probe travels through non-free floor before it reaches free floor (max 1 m).
fn blocked_run(site: &DoorSite, probe: Probe) -> f64 {
    let grid = &site.analysis.grid;
    let step = grid.spec.cell / 2.0;
    let mut travelled = 0.0;
    while travelled < 1.0 && !probe.is_clear_at(grid, travelled) {
        travelled += step;
    }
    travelled
}

/// The shallower side of a doorway without a leaf.
fn doorway_maneuvering_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let site = match door_site(ctx, subject) {
        Ok(site) => site,
        Err(e) => return e,
    };
    let (a, b) = (measure_side(&site, 1.0).depth, measure_side(&site, -1.0).depth);
    range((a.0.min(b.0), a.1.min(b.1))).located(Some(site.opening.center))
}
