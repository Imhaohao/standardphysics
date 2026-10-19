//! Room-level metrics: turning space and toilet-room fixture counts.

use super::support::{LAVATORIES, WATER_CLOSETS, needs_detail, objects_of, wrong_subject};
use crate::metrics::subject::{Subject, SubjectRef};
use crate::metrics::{EvalContext, Extraction, Extractor};
use crate::routes::PASSING_WIDTH;
use crate::scene::{Object, Room};

pub const EXTRACTORS: &[(&str, Extractor)] = &[
    ("room.turning_space_diameter", turning_space_diameter),
    ("room.turning_space_t_shape", turning_space_t_shape),
    ("room.turning_space_overlaps_door_swing_only", turning_space_free_of_fixtures),
    ("fitting_room.turning_space_diameter", fitting_room_turning_space),
    ("toilet_room.compartment_count", compartment_count),
    ("toilet_room.urinal_count", urinal_count),
    ("toilet_room.is_single_user", is_single_user),
    ("toilet_room.has_ambulatory_compartment", has_ambulatory_compartment),
    ("toilet_room.accessible_urinal_count", accessible_urinal_count),
    ("toilet_room.door_encroachment_into_turning_space", door_encroachment),
    ("fitting_room.door_swing_into_turning", needs_detail),
    ("assembly.wheelchair_space_width", needs_detail),
    ("assembly.wheelchair_space_depth", needs_detail),
];

fn room_subject<'a>(ctx: &EvalContext<'a>, subject: &Subject) -> Result<&'a Room, Extraction> {
    match subject.reference {
        SubjectRef::Room { .. } => ctx.room(subject).ok_or_else(wrong_subject),
        _ => Err(wrong_subject()),
    }
}

fn turning_space_diameter(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if subject.has_tag("fitting_room") {
        return fitting_room_turning_space(ctx, subject);
    }
    let room = match room_subject(ctx, subject) {
        Ok(room) => room,
        Err(e) => return e,
    };
    let diameter = ctx.analysis(room.storey).and_then(|a| a.turning_diameter(&room.id));
    super::super::value::metres_or_unknown(diameter, "room is not on the analysed storey")
}

fn turning_space_t_shape(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let room = match room_subject(ctx, subject) {
        Ok(room) => room,
        Err(e) => return e,
    };
    match ctx.analysis(room.storey).and_then(|a| a.t_turn_fits(&room.id)) {
        Some(fits) => Extraction::boolean(fits),
        None => Extraction::unknown("room is not on the analysed storey"),
    }
}

/// Fixtures are obstacles on the grid and door swings are not, so any turning space found is
/// clear of fixtures and overlaps at most a door swing.
fn turning_space_free_of_fixtures(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let room = match room_subject(ctx, subject) {
        Ok(room) => room,
        Err(e) => return e,
    };
    let Some(analysis) = ctx.analysis(room.storey) else {
        return Extraction::unknown("room is not on the analysed storey");
    };
    let circle = analysis.turning_diameter(&room.id).is_some_and(|d| d >= PASSING_WIDTH - 1e-9);
    Extraction::boolean(circle || analysis.t_turn_fits(&room.id).unwrap_or(false))
}

/// Largest circle inside the fitting-room box that stays on free floor.
fn fitting_room_turning_space(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let Some(object) = ctx.object(subject) else { return wrong_subject() };
    let Some(analysis) = ctx.analysis(subject.storey) else { return Extraction::unknown("storey not analysed") };
    let footprint = object.footprint();
    let grid = &analysis.grid;
    let best = grid
        .spec
        .cells_in(footprint.bounds())
        .filter(|&i| grid.is_free(i) && footprint.contains(grid.spec.center(i)))
        .map(|i| analysis.clearance.at(i).min(distance_to_box_edge(&footprint, grid.spec.center(i))))
        .fold(0.0, f64::max);
    Extraction::metres(2.0 * best).located(Some(object.center))
}

fn distance_to_box_edge(footprint: &crate::geometry::OrientedBox2, point: crate::geometry::Vec2) -> f64 {
    let local = footprint.to_local(point);
    (footprint.half_extents.x - local.x.abs()).min(footprint.half_extents.y - local.y.abs()).max(0.0)
}

fn count_in(room: &Room, categories: &[&str]) -> usize {
    room.objects.iter().filter(|o: &&Object| categories.contains(&o.category.as_str())).count()
}

fn compartment_count(ctx: &EvalContext, subject: &Subject) -> Extraction {
    room_subject(ctx, subject)
        .map(|room| Extraction::count(count_in(room, &["toilet_compartment", "urinal"])))
        .unwrap_or_else(|e| e)
}

fn urinal_count(ctx: &EvalContext, subject: &Subject) -> Extraction {
    room_subject(ctx, subject).map(|room| Extraction::count(count_in(room, &["urinal"]))).unwrap_or_else(|e| e)
}

/// One water closet, at most one lavatory, no compartments or urinals. The lock is a separate photo metric.
fn is_single_user(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let room = match room_subject(ctx, subject) {
        Ok(room) => room,
        Err(e) => return e,
    };
    let water_closets = objects_of(room, WATER_CLOSETS).count();
    let lavatories = objects_of(room, LAVATORIES).count();
    let shared = count_in(room, &["toilet_compartment", "urinal"]);
    Extraction::boolean(water_closets == 1 && lavatories <= 1 && shared == 0)
}

const AMBULATORY_WIDTH: (f64, f64) = (0.889, 0.9398);

fn has_ambulatory_compartment(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let room = match room_subject(ctx, subject) {
        Ok(room) => room,
        Err(e) => return e,
    };
    let ambulatory = objects_of(room, &["toilet_compartment"]).any(|c| {
        let width = c.size.x.min(c.size.z);
        width >= AMBULATORY_WIDTH.0 - 0.01 && width <= AMBULATORY_WIDTH.1 + 0.01
    });
    Extraction::boolean(ambulatory)
}

/// Urinals whose rim (within the box) is surely / possibly at most 17 in high.
fn accessible_urinal_count(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let room = match room_subject(ctx, subject) {
        Ok(room) => room,
        Err(e) => return e,
    };
    let limit = crate::units::inches(17.0);
    let spans: Vec<(f64, f64)> = objects_of(room, &["urinal"]).map(super::support::vertical_extent).collect();
    let surely = spans.iter().filter(|(_, top)| *top <= limit).count();
    let possibly = spans.iter().filter(|(bottom, _)| *bottom <= limit).count();
    Extraction::count_range(surely, possibly)
}

/// Doors known to swing out do not encroach; otherwise the swing was not captured.
fn door_encroachment(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let room = match room_subject(ctx, subject) {
        Ok(room) => room,
        Err(e) => return e,
    };
    let doors: Vec<_> = room.openings.iter().filter(|o| o.kind == crate::scene::OpeningKind::Door).collect();
    if doors.iter().all(|d| d.swing.as_ref().is_some_and(|s| !s.swings_in)) {
        Extraction::metres(0.0)
    } else {
        Extraction::unknown("door swing direction was not captured")
    }
}
