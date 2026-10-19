//! Work surfaces, counters, check-out aisles, food lines, benches and signs (902-904, 903, 703).

use super::clear_floor::{clear_floor, faces};
use super::support::{
    COUNTERS, adjoining, items_on, long_axis, long_dimension, needs_detail, object_in_room, projected_span,
    short_dimension, vertical_extent, within_box_height, wrong_subject,
};
use crate::analysis::StoreyAnalysis;
use crate::geometry::{OrientedBox2, Vec2};
use crate::grid::{Probe, area_is_free};
use crate::metrics::subject::Subject;
use crate::metrics::{EvalContext, Extraction, Extractor};
use crate::scene::{Object, Room};
use crate::units::inches;

pub const EXTRACTORS: &[(&str, Extractor)] = &[
    ("dining_table.top_height", top_height),
    ("counter.top_height", top_height),
    ("counter.accessible_length", counter_accessible_length),
    ("counter.accessible_portion_same_depth", counter_same_depth),
    ("counter.approach", counter_approach),
    ("counter.accessible_portion_on_customer_side", counter_on_customer_side),
    ("checkout_aisle.clear_width", aisle_clear_width),
    ("checkout_aisle.counter_height", checkout_counter_height),
    ("food_service_line.tray_slide_height", tray_slide_height),
    ("food_service_line.clear_width", aisle_clear_width),
    ("bar_counter.accessible_section_present", bar_accessible_section),
    ("dining.accessible_table_faces_room", table_faces_room),
    ("bench.length", bench_length),
    ("bench.depth", bench_depth),
    ("bench.seat_height", bench_seat_height),
    ("sign.mounting_height_baseline", sign_height),
    ("sign.lowest_baseline_height", sign_height),
    ("sign.location_latch_side", needs_detail),
    ("sign.clear_floor_18x18", sign_clear_floor),
    ("dining_table.clear_floor_overlaps_route", clear_floor_overlaps_route),
    ("bench.back_support_length", bench_back_support),
];

/// 36 in: highest accessible sales and service counter (904.4.1).
const ACCESSIBLE_COUNTER_HEIGHT: f64 = 0.9144;
/// Benches with a box taller than this include a back.
const BENCH_SEAT_ONLY: f64 = 0.6;

fn object<'a>(ctx: &EvalContext<'a>, subject: &Subject) -> Result<&'a Object, Extraction> {
    ctx.object(subject).ok_or_else(wrong_subject)
}

fn top_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(|o| Extraction::metres(o.top_height).located(Some(o.center))).unwrap_or_else(|e| e)
}

fn is_low(o: &Object) -> bool {
    o.top_height <= ACCESSIBLE_COUNTER_HEIGHT + 1e-6
}

/// Low counter length along the counter, less what sits on top of it. A high counter counts any
/// low counter section that adjoins it.
fn counter_accessible_length(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, counter) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let sections: Vec<&Object> = if is_low(counter) {
        vec![counter]
    } else {
        adjoining(room, counter, COUNTERS, 0.1).filter(|o| is_low(o)).collect()
    };
    let total: f64 = sections.iter().map(|s| clear_length(room, s)).sum();
    Extraction::metres(total).located(Some(counter.center))
}

fn clear_length(room: &Room, counter: &Object) -> f64 {
    let axis = long_axis(counter);
    let origin = counter.center.plan();
    let covered: f64 = items_on(room, counter)
        .map(|item| {
            let (lo, hi) = projected_span(&item.footprint(), origin, axis);
            hi - lo
        })
        .sum();
    (long_dimension(counter) - covered).max(0.0)
}

fn counter_same_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, counter) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    if is_low(counter) {
        return Extraction::boolean(true);
    }
    let low = adjoining(room, counter, COUNTERS, 0.1).find(|o| is_low(o));
    match low {
        Some(section) => Extraction::boolean(short_dimension(section) >= short_dimension(counter) - 0.05),
        None => Extraction::not_applicable("no accessible portion"),
    }
}

fn counter_approach(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, counter) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    match ctx.analysis(room.storey) {
        Some(analysis) => {
            let approach = clear_floor(analysis, counter).approach;
            Extraction::text(if approach == super::clear_floor::Approach::Forward { "forward" } else { "parallel" })
        }
        None => Extraction::unknown("storey not analysed"),
    }
}

/// Some long face of the counter is on the accessible route (the customer side).
fn counter_on_customer_side(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, counter) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(analysis) = ctx.analysis(room.storey) else { return Extraction::unknown("storey not analysed") };
    if analysis.entrances.is_empty() {
        return Extraction::unknown("no entrance on this storey to start a route from");
    }
    let corridor = analysis.route_corridor();
    let touches = faces(&counter.footprint()).iter().any(|f| {
        let probe = f.centre + f.outward * 0.3;
        analysis.grid.spec.locate(probe).is_some_and(|i| corridor[i])
    });
    Extraction::boolean(touches)
}

/// Narrowest slice across the aisle: for each slice along the aisle, the widest free circle in it.
fn aisle_clear_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, aisle) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(analysis) = ctx.analysis(room.storey) else { return Extraction::unknown("storey not analysed") };
    Extraction::metres(narrowest_slice(analysis, &aisle.footprint(), long_axis(aisle))).located(Some(aisle.center))
}

fn narrowest_slice(analysis: &StoreyAnalysis, footprint: &OrientedBox2, along: Vec2) -> f64 {
    let grid = &analysis.grid;
    let origin = footprint.center;
    let (lo, hi) = projected_span(footprint, origin, along);
    let slices = (((hi - lo) / 0.05).ceil() as usize).max(1);
    let mut widest = vec![0.0f64; slices];
    for cell in grid.spec.cells_in(footprint.bounds()).filter(|&i| grid.is_free(i)) {
        let p = grid.spec.center(cell);
        if footprint.contains(p) {
            let slot = (((p - origin).dot(along) - lo) / 0.05) as usize;
            let slot = slot.min(slices - 1);
            widest[slot] = widest[slot].max(analysis.clearance.clear_width_at(cell));
        }
    }
    widest.into_iter().fold(f64::INFINITY, f64::min)
}

fn checkout_counter_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, aisle) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let counter = adjoining(room, aisle, &["counter", "sales_counter", "service_counter"], 0.05).next();
    let surface = counter.unwrap_or(aisle);
    Extraction::metres(surface.top_height).located(Some(surface.center))
}

fn tray_slide_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject)
        .map(|o| {
            let (bottom, top) = vertical_extent(o);
            Extraction::metres_range((top - 0.05).max(bottom), top).located(Some(o.center))
        })
        .unwrap_or_else(|e| e)
}

/// A bar section 60 in long at 28-34 in high next to the bar.
fn bar_accessible_section(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, bar) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let in_band = |o: &Object| {
        o.top_height >= inches(28.0) - 1e-6
            && o.top_height <= inches(34.0) + 1e-6
            && long_dimension(o) >= inches(60.0) - 1e-6
    };
    if in_band(bar) || adjoining(room, bar, &["bar_counter", "counter"], 0.1).any(in_band) {
        Extraction::boolean(true)
    } else {
        Extraction::unknown("no low bar section seen; the owner confirms service at accessible tables")
    }
}

/// Some side of the table has a forward-approach space and faces across the table into open room.
fn table_faces_room(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, table) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(analysis) = ctx.analysis(room.storey) else { return Extraction::unknown("storey not analysed") };
    let grid = &analysis.grid;
    let sides = faces(&table.footprint());
    let faces_room = sides.iter().enumerate().any(|(i, seat)| {
        let opposite = sides[i ^ 1];
        let seat_space =
            Probe::new(seat.centre, seat.outward, inches(15.0)).sweep(grid, inches(48.0)).length >= inches(48.0) - 0.03;
        let view = Probe::new(opposite.centre, opposite.outward, 0.1).sweep(grid, 0.9).length >= 0.9 - 0.03;
        seat_space && view
    });
    Extraction::boolean(faces_room)
}

fn bench_length(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(|o| Extraction::metres(long_dimension(o))).unwrap_or_else(|e| e)
}

fn bench_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(|o| Extraction::metres(short_dimension(o))).unwrap_or_else(|e| e)
}

fn bench_seat_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject)
        .map(|o| if o.size.y <= BENCH_SEAT_ONLY { Extraction::metres(o.top_height) } else { within_box_height(o) })
        .unwrap_or_else(|e| e)
}

fn sign_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(within_box_height).unwrap_or_else(|e| e)
}

/// 18x18 in of free floor centred under the sign; a door within reach of that square leaves it open
/// whether the door's swing crosses it.
fn sign_clear_floor(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, sign) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(analysis) = ctx.analysis(room.storey) else { return Extraction::unknown("storey not analysed") };
    let Some(wall) = super::support::nearest_boundary(room, sign.center.plan()) else {
        return Extraction::unknown("no wall captured");
    };
    let away = (sign.center.plan() - wall.closest_point(sign.center.plan())).normalized();
    let centre = wall.closest_point(sign.center.plan()) + away * (inches(9.0) + 0.06);
    let square = OrientedBox2::new(centre, inches(18.0), inches(18.0), (-away.y).atan2(away.x));
    if !area_is_free(&analysis.grid, &square) {
        return Extraction::boolean(false);
    }
    let near_door =
        room.openings.iter().any(|o| o.kind.is_passable() && o.center.plan().distance(centre) < o.width + inches(9.0));
    if near_door {
        Extraction::unknown("a door swing may cross the space; swing not captured")
    } else {
        Extraction::boolean(true)
    }
}

/// More than a tenth of the table's clear floor space lies in the route corridor.
fn clear_floor_overlaps_route(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, table) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(analysis) = ctx.analysis(room.storey) else { return Extraction::unknown("storey not analysed") };
    if analysis.entrances.is_empty() {
        return Extraction::unknown("no entrance on this storey to start a route from");
    }
    let Some(area) = super::clear_floor::clear_floor_area(ctx, room, table) else {
        return Extraction::unknown("storey not analysed");
    };
    let grid = &analysis.grid;
    let cells: Vec<usize> = grid.spec.cells_in(area.bounds()).filter(|&i| area.contains(grid.spec.center(i))).collect();
    let corridor = analysis.route_corridor();
    let inside = cells.iter().filter(|&&i| corridor[i]).count();
    Extraction::boolean(!cells.is_empty() && inside * 10 > cells.len())
}

/// A bench against a wall, or with a back, is supported along its length.
fn bench_back_support(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, bench) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let against_wall = super::support::nearest_boundary(room, bench.center.plan()).is_some_and(|w| {
        bench.footprint().corners().iter().map(|c| w.distance_to(*c)).fold(f64::INFINITY, f64::min) < 0.1
    });
    if against_wall || bench.size.y > BENCH_SEAT_ONLY {
        Extraction::metres(long_dimension(bench))
    } else {
        Extraction::unknown("no wall or back seen behind the bench; a photo confirms")
    }
}
