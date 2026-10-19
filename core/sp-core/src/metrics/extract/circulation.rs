//! Ramps, curb ramps, stairs, handrails, detectable warnings, parking and elevators (405-410, 502, 504, 505, 705).

use super::support::{long_axis, long_dimension, needs_detail, needs_mesh, nearest_boundary, object_in_room, objects_of, short_dimension, wrong_subject};
use crate::metrics::subject::Subject;
use crate::metrics::{EvalContext, Extraction, Extractor};
use crate::scene::{Object, Room};

pub const EXTRACTORS: &[(&str, Extractor)] = &[
    ("ramp.running_slope", box_slope),
    ("ramp.cross_slope", needs_mesh),
    ("ramp.rise", box_rise),
    ("ramp.clear_width", short_side),
    ("ramp.landing_length", needs_mesh),
    ("ramp.landing_width", needs_mesh),
    ("ramp.landing_slope", needs_mesh),
    ("ramp.bottom_landing_length", needs_mesh),
    ("ramp.top_landing_width", needs_mesh),
    ("handrail.bottom_horizontal_extension", needs_detail),
    ("ramp.change_direction_landing_size", needs_mesh),
    ("ramp.change_direction_landing_length", needs_mesh),
    ("ramp.has_handrails_both_sides", handrails_both_sides),
    ("ramp.curb_height", needs_detail),
    ("ramp.door_swing_into_landing", door_swing_into_landing),
    ("curb_ramp.running_slope", box_slope),
    ("curb_ramp.counter_slope", needs_mesh),
    ("curb_ramp.flare_slope", needs_mesh),
    ("curb_ramp.clear_width", short_side),
    ("curb_ramp.landing_length", needs_mesh),
    ("detectable_warning.depth", short_side),
    ("stairs.riser_height", needs_mesh),
    ("stairs.riser_uniform", needs_mesh),
    ("stairs.tread_depth", needs_mesh),
    ("stairs.nosing_projection", needs_detail),
    ("stairs.has_handrails_both_sides", handrails_both_sides),
    ("handrail.height", handrail_height),
    ("handrail.wall_clearance", handrail_wall_clearance),
    ("handrail.continuous", needs_detail),
    ("handrail.stair_tread_depth", needs_mesh),
    ("handrail.top_extension", needs_detail),
    ("handrail.bottom_extension", needs_detail),
    ("parking_space.width", short_side),
    ("parking_space.length", long_side),
    ("access_aisle.width", access_aisle_width),
    ("parking_space.surface_slope", needs_mesh),
    ("parking_space.vertical_clearance_van", needs_detail),
    ("parking_space.distance_to_entrance_shortest", needs_detail),
    ("elevator.car_inside_width", elevator_inside_width),
    ("elevator.car_inside_depth", elevator_inside_depth),
    ("elevator.door_clear_width", needs_detail),
];

/// Car walls take up to 6 in of an elevator's outer box.
const ELEVATOR_WALL_ALLOWANCE: f64 = 0.15;

fn object<'a>(ctx: &EvalContext<'a>, subject: &Subject) -> Result<&'a Object, Extraction> {
    ctx.object(subject).ok_or_else(wrong_subject)
}

/// Rise over run of the box: right for a straight run captured as one box.
fn box_slope(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject)
        .map(|o| Extraction::ratio(o.size.y / long_dimension(o).max(1e-6)).noted("rise over run of the scanned box"))
        .unwrap_or_else(|e| e)
}

fn box_rise(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(|o| Extraction::metres(o.size.y)).unwrap_or_else(|e| e)
}

fn short_side(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(|o| Extraction::metres(short_dimension(o)).located(Some(o.center))).unwrap_or_else(|e| e)
}

fn long_side(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(|o| Extraction::metres(long_dimension(o)).located(Some(o.center))).unwrap_or_else(|e| e)
}

/// Handrails seen along both long sides; not seeing one is not proof there is none.
fn handrails_both_sides(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, run) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let across = long_axis(run).perpendicular();
    let half = short_dimension(run) / 2.0;
    let side_has_rail = |sign: f64| {
        objects_of(room, &["handrail"]).any(|rail| {
            let offset = (rail.center.plan() - run.center.plan()).dot(across) * sign;
            offset > half - 0.4 && offset < half + 0.4
        })
    };
    if side_has_rail(1.0) && side_has_rail(-1.0) {
        Extraction::boolean(true)
    } else {
        Extraction::unknown("handrails not seen on both sides; a photo confirms")
    }
}

fn door_swing_into_landing(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, ramp) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let reach = long_dimension(ramp) / 2.0 + 1.6;
    let near = room.openings.iter().any(|o| o.kind.is_passable() && o.center.plan().distance(ramp.center.plan()) < reach + o.width);
    if near { Extraction::unknown("a door is near the ramp landing; swing not captured") } else { Extraction::boolean(false) }
}

fn handrail_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(|o| Extraction::metres(o.top_height).located(Some(o.center))).unwrap_or_else(|e| e)
}

fn handrail_wall_clearance(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, rail) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    wall_gap(room, rail).map(|gap| Extraction::metres(gap).located(Some(rail.center))).unwrap_or_else(|| Extraction::unknown("no wall captured"))
}

fn wall_gap(room: &Room, rail: &Object) -> Option<f64> {
    let wall = nearest_boundary(room, rail.center.plan())?;
    Some(rail.footprint().corners().iter().map(|c| wall.distance_to(*c)).fold(f64::INFINITY, f64::min))
}

fn access_aisle_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, element) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    if element.category == "access_aisle" {
        return Extraction::metres(short_dimension(element));
    }
    let grown = element.footprint().grown(0.3);
    match objects_of(room, &["access_aisle"]).find(|a| a.footprint().overlaps(&grown)) {
        Some(aisle) => Extraction::metres(short_dimension(aisle)).located(Some(aisle.center)),
        None => Extraction::unknown("no access aisle seen beside the space"),
    }
}

fn elevator_inside_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(|o| inside(short_dimension(o))).unwrap_or_else(|e| e)
}

fn elevator_inside_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(|o| inside(long_dimension(o))).unwrap_or_else(|e| e)
}

fn inside(outer: f64) -> Extraction {
    Extraction::metres_range((outer - ELEVATOR_WALL_ALLOWANCE).max(0.0), outer).noted("outer box less up to 6 in of car wall")
}
