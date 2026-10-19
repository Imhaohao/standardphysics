//! Route-leg metrics (402, 403), headroom (307.4) and changes in level (303).

use super::support::{floor_point, needs_mesh, vertical_extent, wrong_subject};
use crate::analysis::{RouteRecord, StoreyAnalysis};
use crate::geometry::Vec2;
use crate::grid::BLOCKS_FLOOR_BELOW;
use crate::metrics::subject::{Subject, SubjectRef};
use crate::metrics::{EvalContext, Extraction, Extractor};
use crate::routes::{ROUTE_MIN_CLEAR_WIDTH, RouteLeg, Turn180};
use crate::units::inches;

pub const EXTRACTORS: &[(&str, Extractor)] = &[
    ("route.min_clear_width", min_clear_width),
    ("route.reduced_width_run_length", reduced_width_run_length),
    ("route.reduced_width_separation_length", reduced_width_separation_length),
    ("route.turn_around_element_width", turn_element_width),
    ("route.turn_clear_width_approach", turn_approach_width),
    ("route.turn_clear_width_at_turn", turn_width),
    ("route.turn_clear_width_leaving", turn_leaving_width),
    ("route.max_distance_between_passing_spaces", max_distance_between_passing_spaces),
    ("route.running_slope", needs_mesh),
    ("route.cross_slope", needs_mesh),
    ("route.contains_stairs_or_escalator", contains_stairs),
    ("route.connects_entrance", connects_entrance),
    ("route.same_area_as_general_circulation", same_area_as_general),
    ("route.length_ratio_vs_general", length_ratio_vs_general),
    ("headroom.vertical_clearance", vertical_clearance),
    ("headroom.guarded_below_80", guarded_below_80),
    ("floor.change_in_level", change_in_level),
    ("floor.change_in_level_bevel_slope", needs_mesh),
];

/// Metres the accessible route may stray from the general circulation path and still be "in the same area".
const SAME_AREA_DISTANCE: f64 = 3.0;

type Leg<'a> = (&'a StoreyAnalysis, &'a RouteRecord, &'a RouteLeg);

fn leg<'a>(ctx: &EvalContext<'a>, subject: &Subject) -> Result<Leg<'a>, Extraction> {
    let (analysis, record) = ctx.route(subject).ok_or_else(wrong_subject)?;
    if analysis.entrances.is_empty() {
        return Err(Extraction::unknown("no entrance on this storey to start a route from"));
    }
    match &record.leg {
        Some(leg) => Ok((analysis, record, leg)),
        None => Err(Extraction::metres(0.0).noted("no wheelchair path reaches this destination")),
    }
}

fn min_clear_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (_, _, leg) = match leg(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let narrowest = leg.pinches.iter().min_by(|a, b| a.clear_width.total_cmp(&b.clear_width));
    let location = narrowest.map(|p| p.location).or_else(|| leg.points.last().copied());
    match leg.min_clear_width {
        Some(width) => Extraction::metres(width).located(location.and_then(floor_point)),
        None => Extraction::not_applicable("route lies entirely within door openings"),
    }
}

fn reduced_width_run_length(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let longest = |leg: &RouteLeg| leg.reduced_width_runs.iter().map(|(a, b)| b - a).fold(0.0, f64::max);
    leg(ctx, subject).map(|(_, _, l)| Extraction::metres(longest(l))).unwrap_or_else(not_reached)
}

fn reduced_width_separation_length(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (_, _, leg) = match leg(ctx, subject) {
        Ok(found) => found,
        Err(e) => return not_reached(e),
    };
    let runs = &leg.reduced_width_runs;
    let gaps = runs.windows(2).map(|pair| pair[1].0 - pair[0].1);
    match gaps.reduce(f64::min) {
        Some(gap) => Extraction::metres(gap),
        None => Extraction::not_applicable("fewer than two reduced-width stretches"),
    }
}

/// A destination no wheelchair can reach has no width runs to measure; the width rule reports it.
fn not_reached(error: Extraction) -> Extraction {
    match error {
        Extraction::Measured(_) => Extraction::not_applicable("no wheelchair path reaches this destination"),
        other => other,
    }
}

fn with_turn(ctx: &EvalContext, subject: &Subject, read: fn(&Turn180) -> f64) -> Extraction {
    let (_, _, leg) = match leg(ctx, subject) {
        Ok(found) => found,
        Err(e) => return not_reached(e),
    };
    match &leg.turn {
        Some(turn) => Extraction::metres(read(turn)).located(floor_point(turn.apex)),
        None => Extraction::not_applicable("route makes no 180-degree turn"),
    }
}

fn turn_element_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    with_turn(ctx, subject, |t| t.element_width)
}

fn turn_approach_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    with_turn(ctx, subject, |t| t.approach_width)
}

fn turn_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    with_turn(ctx, subject, |t| t.turn_width)
}

fn turn_leaving_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    with_turn(ctx, subject, |t| t.leaving_width)
}

fn max_distance_between_passing_spaces(ctx: &EvalContext, subject: &Subject) -> Extraction {
    leg(ctx, subject).map(|(_, _, l)| Extraction::metres(l.max_distance_between_passing_spaces)).unwrap_or_else(not_reached)
}

fn contains_stairs(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if subject.reference == SubjectRef::Site {
        return site_contains_stairs(ctx);
    }
    let Some((analysis, record)) = ctx.route(subject) else { return wrong_subject() };
    route_needs_stairs(analysis, record)
}

fn route_needs_stairs(analysis: &StoreyAnalysis, record: &RouteRecord) -> Extraction {
    if record.leg.is_some() {
        return Extraction::boolean(false);
    }
    match analysis.walking_route(record) {
        Some(_) if has_stairs(analysis) => Extraction::boolean(true),
        _ => Extraction::unknown("destination is not reachable on the scanned floor"),
    }
}

fn has_stairs(analysis: &StoreyAnalysis) -> bool {
    analysis.grid.states.contains(&crate::grid::CellState::Stairs)
}

fn site_contains_stairs(ctx: &EvalContext) -> Extraction {
    let lifts = ctx.objects_of(&["elevator", "platform_lift"]).next().is_some();
    if ctx.scene.storeys().len() > 1 && !lifts {
        return Extraction::boolean(true).noted("several storeys and no elevator or lift seen");
    }
    let any = ctx.analyses.values().flat_map(|a| a.routes.iter().map(move |r| (a, r))).any(|(a, r)| {
        matches!(route_needs_stairs(a, r), Extraction::Measured(ref m) if m.value == crate::metrics::Value::Bool { value: true })
    });
    Extraction::boolean(any)
}

/// A route of 36 in or more (doors judged separately) from an entrance reaches the subject.
fn connects_entrance(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let found = match subject.reference {
        SubjectRef::Route { .. } => ctx.route(subject),
        _ => ctx.analysis(subject.storey).and_then(|a| a.route_to(&subject.id).map(|r| (a, r))),
    };
    let Some((analysis, record)) = found else { return wrong_subject() };
    if analysis.entrances.is_empty() {
        return Extraction::unknown("no entrance on this storey to start a route from");
    }
    let wide_enough = record.leg.as_ref().is_some_and(|leg| leg.min_clear_width.is_none_or(|w| w >= ROUTE_MIN_CLEAR_WIDTH - 1e-9));
    Extraction::boolean(wide_enough)
}

fn same_area_as_general(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (analysis, record, leg) = match leg(ctx, subject) {
        Ok(found) => found,
        Err(e) => return not_reached(e),
    };
    let Some((_, walking)) = analysis.walking_route(record) else { return Extraction::unknown("no walking path to compare") };
    Extraction::boolean(directed_hausdorff(&leg.points, &walking) <= SAME_AREA_DISTANCE)
}

/// Largest distance from a point of `from` to the nearest point of `to`, on every 4th point.
fn directed_hausdorff(from: &[Vec2], to: &[Vec2]) -> f64 {
    let sampled: Vec<Vec2> = to.iter().step_by(4).copied().collect();
    from.iter().step_by(4).map(|p| sampled.iter().map(|q| p.distance(*q)).fold(f64::INFINITY, f64::min)).fold(0.0, f64::max)
}

fn length_ratio_vs_general(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (analysis, record, leg) = match leg(ctx, subject) {
        Ok(found) => found,
        Err(e) => return not_reached(e),
    };
    match analysis.walking_route(record) {
        Some((walking, _)) if walking > 0.5 => Extraction::ratio(leg.length / walking),
        Some(_) => Extraction::not_applicable("destination is at the entrance"),
        None => Extraction::unknown("no walking path to compare"),
    }
}

fn vertical_clearance(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if let Some(opening) = ctx.opening(subject) {
        return Extraction::metres(opening.height).located(Some(opening.center));
    }
    if let Some(object) = ctx.object(subject) {
        return object_headroom(object);
    }
    match ctx.route(subject) {
        Some((_, record)) => route_headroom(ctx, subject, record),
        None => wrong_subject(),
    }
}

fn object_headroom(object: &crate::scene::Object) -> Extraction {
    if object.category == "stairs" {
        return needs_mesh_for_stairs();
    }
    Extraction::metres(object.bottom_height()).located(Some(object.center))
}

fn needs_mesh_for_stairs() -> Extraction {
    Extraction::unknown("needs the mesh under the stair to measure headroom")
}

/// Lowest of the ceilings and overhead objects (underside at or above 27 in) over the route.
fn route_headroom(ctx: &EvalContext, subject: &Subject, record: &RouteRecord) -> Extraction {
    let Some(leg) = &record.leg else { return Extraction::not_applicable("no wheelchair path to measure") };
    let points: Vec<Vec2> = leg.points.iter().step_by(4).copied().collect();
    let rooms = ctx.scene.rooms_on(subject.storey);
    let mut lowest: Option<(f64, Vec2)> = None;
    for room in rooms {
        for p in points.iter().filter(|p| room.floor.contains(**p)) {
            lowest = lower(lowest, room.ceiling_height, *p);
        }
        for object in room.objects.iter().filter(|o| o.bottom_height() >= BLOCKS_FLOOR_BELOW) {
            let over = points.iter().find(|p| object.footprint().distance_to(**p) < inches(18.0));
            if let Some(p) = over {
                lowest = lower(lowest, vertical_extent(object).0, *p);
            }
        }
    }
    match lowest {
        Some((height, at)) => Extraction::metres(height).located(floor_point(at)),
        None => Extraction::unknown("route does not cross a scanned room"),
    }
}

fn lower(current: Option<(f64, Vec2)>, height: f64, at: Vec2) -> Option<(f64, Vec2)> {
    match current {
        Some((h, _)) if h <= height => current,
        _ => Some((height, at)),
    }
}

fn guarded_below_80(ctx: &EvalContext, subject: &Subject) -> Extraction {
    match vertical_clearance(ctx, subject) {
        Extraction::Measured(m) if matches!(m.value, crate::metrics::Value::Number { lo, .. } if lo >= inches(80.0)) => {
            Extraction::not_applicable("headroom is at least 80 in")
        }
        Extraction::NotApplicable(reason) => Extraction::NotApplicable(reason),
        _ => Extraction::unknown("headroom is under 80 in or unknown; needs a photo of the guard"),
    }
}

/// Thresholds and mats from their box height; floors and routes need the floor mesh.
fn change_in_level(ctx: &EvalContext, subject: &Subject) -> Extraction {
    match ctx.object(subject) {
        Some(object) => Extraction::metres(object.size.y).located(Some(object.center)),
        None => needs_mesh(ctx, subject),
    }
}
