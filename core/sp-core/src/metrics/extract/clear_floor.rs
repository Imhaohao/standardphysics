//! Clear floor space at an element (305), knee and toe clearance (306).

use super::support::{needs_mesh, object_in_room, wrong_subject};
use crate::analysis::StoreyAnalysis;
use crate::geometry::{OrientedBox2, Vec2};
use crate::grid::{OccupancyGrid, Probe};
use crate::metrics::subject::Subject;
use crate::metrics::{EvalContext, Extraction, Extractor};
use crate::routes::ROUTE_MIN_CLEAR_WIDTH;
use crate::scene::{Object, Room};
use crate::units::inches;

pub const EXTRACTORS: &[(&str, Extractor)] = &[
    ("clear_floor.width", width),
    ("clear_floor.depth", depth),
    ("clear_floor.alcove_depth", alcove_depth),
    ("clear_floor.alcove_width", alcove_width),
    ("clear_floor.adjoins_route", adjoins_route),
    ("clear_floor.approach", approach),
    ("floor.slope_at_clear_floor_space", needs_mesh),
    ("element.on_accessible_route", on_accessible_route),
    ("knee_clearance.height", knee_height),
    ("knee_clearance.depth", knee_depth),
    ("knee_clearance.depth_at_9in", knee_depth_at_9in),
    ("knee_clearance.width", knee_width),
    ("toe_clearance.height", toe_height),
    ("toe_clearance.depth", toe_depth),
];

/// Elements used face-on with knees under them (305.3 forward approach).
const FORWARD_ONLY: &[&str] = &["lavatory", "sink", "drinking_fountain", "dining_table", "table", "work_surface", "kiosk", "atm", "bar_counter"];
const SKIP_MOUNTING: f64 = 0.15;
const PROBE_LENGTH: f64 = 2.0;
const SIDE_PROBE: f64 = 1.5;

type Range = (f64, f64);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Approach {
    Forward,
    Parallel,
}

impl Approach {
    fn name(self) -> &'static str {
        match self {
            Approach::Forward => "forward",
            Approach::Parallel => "parallel",
        }
    }

    /// Size of the 30x48 space (along the element face, out from it).
    fn footprint(self) -> (f64, f64) {
        match self {
            Approach::Forward => (inches(30.0), inches(48.0)),
            Approach::Parallel => (inches(48.0), inches(30.0)),
        }
    }
}

/// One side of an element's footprint.
#[derive(Debug, Clone, Copy)]
pub struct Face {
    pub centre: Vec2,
    pub outward: Vec2,
    pub along: Vec2,
    pub length: f64,
}

pub fn faces(footprint: &OrientedBox2) -> [Face; 4] {
    let (x_axis, z_axis) = footprint.axes();
    let h = footprint.half_extents;
    let face = |outward: Vec2, offset: f64, length: f64| Face { centre: footprint.center + outward * offset, outward, along: outward.perpendicular(), length };
    [face(z_axis, h.y, 2.0 * h.x), face(-z_axis, h.y, 2.0 * h.x), face(x_axis, h.x, 2.0 * h.y), face(-x_axis, h.x, 2.0 * h.y)]
}

/// The face with the most free floor in front of it (front faces first on ties).
pub fn front_face(grid: &OccupancyGrid, footprint: &OrientedBox2) -> Face {
    let free_depth = |f: &Face| Probe::new(f.centre, f.outward, f.length.min(inches(30.0)) / 2.0).sweep_past(grid, SKIP_MOUNTING, PROBE_LENGTH).length;
    let all = faces(footprint);
    let mut best = all[0];
    let mut best_depth = free_depth(&best);
    for face in &all[1..] {
        let d = free_depth(face);
        if d > best_depth + grid.spec.cell {
            best = *face;
            best_depth = d;
        }
    }
    best
}

/// Clear floor at an element, in wheelchair terms: `width` is the 30 in dimension, `depth` the 48 in one.
#[derive(Debug, Clone, Copy)]
pub struct ClearFloor {
    pub approach: Approach,
    pub width: Range,
    pub depth: Range,
    pub face: Face,
}

fn out_and_across(grid: &OccupancyGrid, face: &Face, half_width: f64, band_cap: f64) -> (Range, Range) {
    let out = Probe::new(face.centre, face.outward, half_width).sweep_past(grid, SKIP_MOUNTING, PROBE_LENGTH);
    let out = (out.length, out.upper_bound());
    let band = out.0.min(band_cap);
    if band < 0.05 {
        return (out, (0.0, 0.0));
    }
    let origin = face.centre + face.outward * (grid.spec.cell + band / 2.0);
    let side = |dir: f64| Probe::new(origin, face.along * dir, band / 2.0 - 0.01).sweep(grid, SIDE_PROBE);
    let (left, right) = (side(1.0), side(-1.0));
    (out, (left.length + right.length, left.upper_bound() + right.upper_bound()))
}

fn measure(grid: &OccupancyGrid, face: &Face, approach: Approach) -> ClearFloor {
    match approach {
        Approach::Forward => {
            let (out, across) = out_and_across(grid, face, inches(15.0), inches(48.0));
            ClearFloor { approach, width: across, depth: out, face: *face }
        }
        Approach::Parallel => {
            let (out, across) = out_and_across(grid, face, inches(24.0), inches(30.0));
            ClearFloor { approach, width: out, depth: across, face: *face }
        }
    }
}

fn fits(c: &ClearFloor) -> bool {
    c.width.0 >= inches(30.0) - 1e-6 && c.depth.0 >= inches(48.0) - 1e-6
}

pub fn clear_floor(analysis: &StoreyAnalysis, object: &Object) -> ClearFloor {
    let grid = &analysis.grid;
    let face = front_face(grid, &object.footprint());
    if FORWARD_ONLY.contains(&object.category.as_str()) {
        return measure(grid, &face, Approach::Forward);
    }
    let parallel = measure(grid, &face, Approach::Parallel);
    if fits(&parallel) {
        return parallel;
    }
    let forward = measure(grid, &face, Approach::Forward);
    if fits(&forward) { forward } else { parallel }
}

pub fn needs_clear_floor(ctx: &EvalContext, object: &Object) -> bool {
    ctx.clear_floor_categories.contains(&object.category)
}

/// The required 30x48 rectangle placed at the element's front face.
pub fn clear_floor_area(ctx: &EvalContext, room: &Room, object: &Object) -> Option<OrientedBox2> {
    let analysis = ctx.analysis(room.storey)?;
    let c = clear_floor(analysis, object);
    let (along, out) = c.approach.footprint();
    let yaw = (-c.face.along.y).atan2(c.face.along.x);
    Some(OrientedBox2::new(c.face.centre + c.face.outward * (out / 2.0), along, out, yaw))
}

fn with_clear_floor(ctx: &EvalContext, subject: &Subject, read: fn(&ClearFloor) -> Extraction) -> Extraction {
    let (room, object) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    match ctx.analysis(room.storey) {
        Some(analysis) => read(&clear_floor(analysis, object)).located(Some(object.center)),
        None => Extraction::unknown("storey not analysed"),
    }
}

fn width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    with_clear_floor(ctx, subject, |c| Extraction::metres_range(c.width.0, c.width.1))
}

fn depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    with_clear_floor(ctx, subject, |c| Extraction::metres_range(c.depth.0, c.depth.1))
}

fn approach(ctx: &EvalContext, subject: &Subject) -> Extraction {
    with_clear_floor(ctx, subject, |c| Extraction::text(c.approach.name()))
}

/// Depth over which free floor in front of the element stays bounded on both sides, and the
/// narrowest width between those sides.
fn alcove(analysis: &StoreyAnalysis, object: &Object) -> (f64, Option<f64>) {
    let grid = &analysis.grid;
    let c = clear_floor(analysis, object);
    let reach = c.approach.footprint().0 / 2.0 + 0.3;
    let mut depth = 0.0;
    let mut narrowest: Option<f64> = None;
    let mut d = grid.spec.cell;
    while d <= c.depth.0.max(c.width.0) + 0.3 {
        let origin = c.face.centre + c.face.outward * d;
        let side = |dir: f64| Probe::new(origin, c.face.along * dir, 0.0).sweep(grid, reach).upper_bound();
        let (left, right) = (side(1.0), side(-1.0));
        if left >= reach || right >= reach {
            break;
        }
        depth = d;
        narrowest = Some(narrowest.map_or(left + right, |n: f64| n.min(left + right)));
        d += 0.05;
    }
    (depth, narrowest)
}

fn alcove_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, object) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(analysis) = ctx.analysis(room.storey) else { return Extraction::unknown("storey not analysed") };
    Extraction::metres(alcove(analysis, object).0)
}

fn alcove_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, object) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(analysis) = ctx.analysis(room.storey) else { return Extraction::unknown("storey not analysed") };
    match alcove(analysis, object).1 {
        Some(width) => Extraction::metres(width),
        None => Extraction::not_applicable("element is not in an alcove"),
    }
}

fn touches_route(ctx: &EvalContext, room: &Room, object: &Object) -> Option<bool> {
    let analysis = ctx.analysis(room.storey)?;
    let area = clear_floor_area(ctx, room, object)?.grown(analysis.grid.spec.cell);
    let grid = &analysis.grid;
    let corridor = analysis.route_corridor();
    Some(grid.spec.cells_in(area.bounds()).any(|i| corridor[i] && area.contains(grid.spec.center(i))))
}

fn adjoins_route(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, object) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    if ctx.analysis(room.storey).is_some_and(|a| a.entrances.is_empty()) {
        return Extraction::unknown("no entrance on this storey to start a route from");
    }
    touches_route(ctx, room, object).map(Extraction::boolean).unwrap_or_else(|| Extraction::unknown("storey not analysed"))
}

fn on_accessible_route(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, object) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(analysis) = ctx.analysis(room.storey) else { return Extraction::unknown("storey not analysed") };
    if analysis.entrances.is_empty() {
        return Extraction::unknown("no entrance on this storey to start a route from");
    }
    let route_ok = analysis
        .route_to(&object.id)
        .and_then(|r| r.leg.as_ref())
        .is_some_and(|leg| leg.min_clear_width.is_none_or(|w| w >= ROUTE_MIN_CLEAR_WIDTH - 1e-9));
    Extraction::boolean(route_ok && touches_route(ctx, room, object).unwrap_or(false))
}

/// Underside height when the element is raised off the floor; a box reaching the floor hides it.
fn raised_underside(ctx: &EvalContext, subject: &Subject, minimum: f64) -> Result<f64, Extraction> {
    let object = ctx.object(subject).ok_or_else(wrong_subject)?;
    let bottom = object.bottom_height();
    if bottom >= minimum {
        Ok(bottom)
    } else {
        Err(Extraction::unknown("the box reaches the floor, hiding the space underneath; needs a photo"))
    }
}

fn element_depth(ctx: &EvalContext, subject: &Subject) -> Option<f64> {
    let (room, object) = object_in_room(ctx, subject).ok()?;
    let analysis = ctx.analysis(room.storey)?;
    let face = front_face(&analysis.grid, &object.footprint());
    let along_x = face.outward.dot(object.footprint().axes().0).abs() > 0.5;
    Some(if along_x { object.size.x } else { object.size.z })
}

fn knee_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    raised_underside(ctx, subject, 0.05).map(Extraction::metres).unwrap_or_else(|e| e)
}

fn knee_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    depth_under(ctx, subject, inches(27.0))
}

fn knee_depth_at_9in(ctx: &EvalContext, subject: &Subject) -> Extraction {
    depth_under(ctx, subject, inches(9.0))
}

fn depth_under(ctx: &EvalContext, subject: &Subject, at_height: f64) -> Extraction {
    if let Err(e) = raised_underside(ctx, subject, at_height) {
        return e;
    }
    element_depth(ctx, subject).map(Extraction::metres).unwrap_or_else(wrong_subject)
}

fn knee_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if let Err(e) = raised_underside(ctx, subject, inches(27.0)) {
        return e;
    }
    let (room, object) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(analysis) = ctx.analysis(room.storey) else { return Extraction::unknown("storey not analysed") };
    Extraction::metres(front_face(&analysis.grid, &object.footprint()).length)
}

fn toe_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    raised_underside(ctx, subject, 0.05).map(Extraction::metres).unwrap_or_else(|e| e)
}

fn toe_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    depth_under(ctx, subject, inches(9.0))
}
