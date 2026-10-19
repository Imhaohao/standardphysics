//! Water closets, grab bars, dispensers, compartments, urinals and lavatories (603-606).

use super::support::{
    WATER_CLOSETS, boundary_segments, long_axis, long_dimension, needs_detail, object_in_room, objects_of,
    projected_span, short_dimension, vertical_extent, within_box_height, wrong_subject,
};
use crate::geometry::{Segment2, Vec2};
use crate::metrics::subject::Subject;
use crate::metrics::{EvalContext, Extraction, Extractor};
use crate::scene::{Object, Room};
use crate::units::inches;

pub const EXTRACTORS: &[(&str, Extractor)] = &[
    ("water_closet.centerline_from_side_wall", centerline_from_side_wall),
    ("water_closet.clearance_width", clearance_width),
    ("water_closet.clearance_depth", clearance_depth),
    ("water_closet.clearance_has_other_fixture", clearance_has_other_fixture),
    ("water_closet.seat_height", seat_height),
    ("grab_bar.side_length", side_length),
    ("grab_bar.side_distance_from_rear_wall", side_distance_from_rear_wall),
    ("grab_bar.side_extension_from_rear_wall", side_extension_from_rear_wall),
    ("grab_bar.rear_length", rear_length),
    ("grab_bar.rear_extension_side_wall_side", rear_extension_side_wall_side),
    ("grab_bar.rear_extension_open_side", rear_extension_open_side),
    ("grab_bar.height", grab_bar_height),
    ("grab_bar.clearance_above", grab_bar_clearance_above),
    ("grab_bar.clearance_below", grab_bar_clearance_below),
    ("grab_bar.present_side", grab_bar_present_side),
    ("grab_bar.present_rear", grab_bar_present_rear),
    ("toilet_paper_dispenser.centerline_from_wc_front", dispenser_from_wc_front),
    ("toilet_paper_dispenser.outlet_height", dispenser_outlet_height),
    ("toilet_compartment.width", compartment_width),
    ("toilet_compartment.depth", compartment_depth),
    ("toilet_compartment.toe_clearance_height", needs_detail),
    ("toilet_compartment.door_location_from_side", needs_detail),
    ("toilet_compartment.kind", compartment_kind),
    ("toilet_compartment.front_maneuvering_depth", compartment_front_depth),
    ("water_closet.compartment_kind", wc_compartment_kind),
    ("toilet_paper_dispenser.below_grab_bar", dispenser_below_grab_bar),
    ("toilet_compartment.wc_mounting", wc_mounting),
    ("urinal.rim_height", within_box),
    ("urinal.rim_depth", urinal_rim_depth),
    ("lavatory.rim_height", lavatory_rim_height),
    ("lavatory.centerline_from_side_wall", lavatory_centerline_from_side_wall),
    ("grab_bar.side_front_beyond_wc", side_bar_beyond_wc),
    ("water_closet.front_maneuvering_depth", wc_front_maneuvering_depth),
    ("lavatory.distance_from_wc_centerline", lavatory_from_wc_centerline),
];

/// Items 604.3.2 allows inside the water closet clearance.
const ALLOWED_IN_CLEARANCE: &[&str] = &[
    "grab_bar",
    "dispenser",
    "toilet_paper_dispenser",
    "coat_hook",
    "shelf",
    "sign",
    "hand_dryer",
    "mirror",
    "toilet_compartment",
    "wall_mounted_object",
];
const CLEARANCE_WIDTH: f64 = 1.524;
const CLEARANCE_DEPTH: f64 = 1.4224;
const SEARCH_LIMIT: f64 = 3.0;
const SAMPLE_SPACING: f64 = 0.02;
const NEAR_WALL: f64 = 0.3;

/// A water closet's frame: x across from the side wall, y out from the rear wall.
struct WcFrame {
    rear_origin: Vec2,
    facing: Vec2,
    lateral: Vec2,
    rear: Segment2,
    side: Option<Segment2>,
    centre_x: Option<f64>,
}

impl WcFrame {
    fn of(room: &Room, wc: &Object) -> Option<WcFrame> {
        let centre = wc.center.plan();
        let segments = enclosure(room, wc);
        let rear = *segments.iter().min_by(|a, b| a.distance_to(centre).total_cmp(&b.distance_to(centre)))?;
        let facing = (centre - rear.closest_point(centre)).normalized();
        let side = segments
            .iter()
            .filter(|s| s.direction().dot(facing).abs() > 0.8)
            .min_by(|a, b| a.distance_to(centre).total_cmp(&b.distance_to(centre)))
            .copied();
        let lateral = side.map(|s| (centre - s.closest_point(centre)).normalized()).unwrap_or(facing.perpendicular());
        let rear_origin = side.map(|s| line_intersection(&rear, &s)).unwrap_or(rear.closest_point(centre));
        let mut frame = WcFrame { rear_origin, facing, lateral, rear, side, centre_x: None };
        frame.centre_x = side.map(|_| frame.local(centre).x);
        Some(frame)
    }

    fn local(&self, p: Vec2) -> Vec2 {
        let offset = p - self.rear_origin;
        Vec2::new(offset.dot(self.lateral), offset.dot(self.facing))
    }
}

/// Walls of the room plus the partitions of a compartment holding the water closet.
fn enclosure(room: &Room, wc: &Object) -> Vec<Segment2> {
    let mut segments = boundary_segments(room);
    let compartment = objects_of(room, &["toilet_compartment"]).find(|c| c.footprint().contains(wc.center.plan()));
    if let Some(c) = compartment {
        let corners = c.footprint().corners();
        segments.extend((0..4).map(|i| Segment2::new(corners[i], corners[(i + 1) % 4])));
    }
    segments
}

fn line_intersection(a: &Segment2, b: &Segment2) -> Vec2 {
    let (p, r) = (a.start, a.end - a.start);
    let (q, s) = (b.start, b.end - b.start);
    let denominator = r.cross(s);
    if denominator.abs() < 1e-12 {
        return a.closest_point(b.start);
    }
    p + r * ((q - p).cross(s) / denominator)
}

fn water_closet<'a>(ctx: &EvalContext<'a>, subject: &Subject) -> Result<(&'a Room, &'a Object, WcFrame), Extraction> {
    let (room, wc) = object_in_room(ctx, subject)?;
    let frame =
        WcFrame::of(room, wc).ok_or_else(|| Extraction::unknown("no walls captured around the water closet"))?;
    Ok((room, wc, frame))
}

fn centerline_from_side_wall(ctx: &EvalContext, subject: &Subject) -> Extraction {
    match water_closet(ctx, subject) {
        Ok((_, wc, frame)) => match frame.centre_x {
            Some(x) => Extraction::metres(x).located(Some(wc.center)),
            None => Extraction::unknown("no side wall found beside the water closet"),
        },
        Err(e) => e,
    }
}

/// Points of every obstruction (other walls, non-allowed objects) in the water closet frame.
fn obstruction_points(room: &Room, wc: &Object, frame: &WcFrame) -> Vec<Vec2> {
    let walls = enclosure(room, wc).into_iter().filter(|s| *s != frame.rear && Some(*s) != frame.side);
    let wall_points = walls.flat_map(|s| s.samples(SAMPLE_SPACING));
    let objects = room.objects.iter().filter(|o| o.id != wc.id && !ALLOWED_IN_CLEARANCE.contains(&o.category.as_str()));
    let object_points = objects.flat_map(|o| o.footprint().boundary_points(SAMPLE_SPACING));
    wall_points.chain(object_points).map(|p| frame.local(p)).collect()
}

fn clear_extent(points: &[Vec2], along: impl Fn(&Vec2) -> f64, across: impl Fn(&Vec2) -> f64, band: f64) -> f64 {
    points
        .iter()
        .filter(|p| across(p) > 0.01 && across(p) < band && along(p) > 0.01)
        .map(&along)
        .fold(SEARCH_LIMIT, f64::min)
}

fn clearance_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, wc, frame) = match water_closet(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    if frame.side.is_none() {
        return Extraction::unknown("no side wall found beside the water closet");
    }
    let points = obstruction_points(room, wc, &frame);
    Extraction::metres(clear_extent(&points, |p| p.x, |p| p.y, CLEARANCE_DEPTH)).located(Some(wc.center))
}

fn clearance_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, wc, frame) = match water_closet(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let points = obstruction_points(room, wc, &frame);
    let band = if frame.side.is_some() { CLEARANCE_WIDTH } else { f64::INFINITY };
    Extraction::metres(clear_extent(&points, |p| p.y, |p| p.x.abs(), band)).located(Some(wc.center))
}

fn clearance_has_other_fixture(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, wc, frame) = match water_closet(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let fixtures =
        room.objects.iter().filter(|o| o.id != wc.id && !ALLOWED_IN_CLEARANCE.contains(&o.category.as_str()));
    let inside = |p: Vec2| p.x > 0.01 && p.x < CLEARANCE_WIDTH && p.y > 0.01 && p.y < CLEARANCE_DEPTH;
    let mut points = fixtures.flat_map(|o| o.footprint().boundary_points(SAMPLE_SPACING));
    Extraction::boolean(points.any(|p| inside(frame.local(p))))
}

fn seat_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    within_box(ctx, subject)
}

fn within_box(ctx: &EvalContext, subject: &Subject) -> Extraction {
    ctx.object(subject).map(within_box_height).unwrap_or_else(wrong_subject)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BarWall {
    Side,
    Rear,
}

/// A grab bar, the frame of its nearest water closet, the wall it is on and its span in that frame.
type PlacedBar<'a> = (&'a Object, WcFrame, BarWall, (f64, f64));

/// Which wall of the nearest water closet a grab bar is on, with the bar's span in that frame.
fn grab_bar<'a>(ctx: &EvalContext<'a>, subject: &Subject) -> Result<PlacedBar<'a>, Extraction> {
    let (room, bar) = object_in_room(ctx, subject)?;
    let wc = objects_of(room, WATER_CLOSETS)
        .min_by(|a, b| {
            a.center.plan().distance(bar.center.plan()).total_cmp(&b.center.plan().distance(bar.center.plan()))
        })
        .ok_or_else(|| Extraction::not_applicable("no water closet in the room"))?;
    let frame =
        WcFrame::of(room, wc).ok_or_else(|| Extraction::unknown("no walls captured around the water closet"))?;
    let local = frame.local(bar.center.plan());
    let runs_along_facing = long_axis(bar).dot(frame.facing).abs() > 0.7;
    let wall = match (runs_along_facing, local.x < NEAR_WALL, local.y < NEAR_WALL) {
        (true, true, _) => BarWall::Side,
        (false, _, true) => BarWall::Rear,
        _ => return Err(Extraction::not_applicable("grab bar is not on the side or rear wall of a water closet")),
    };
    let axis = if wall == BarWall::Side { frame.facing } else { frame.lateral };
    let span = projected_span(&bar.footprint(), frame.rear_origin, axis);
    Ok((bar, frame, wall, span))
}

fn bar_metric(
    ctx: &EvalContext,
    subject: &Subject,
    wall: BarWall,
    read: fn(&Object, &WcFrame, (f64, f64)) -> Option<f64>,
) -> Extraction {
    match grab_bar(ctx, subject) {
        Ok((bar, frame, found, span)) if found == wall => match read(bar, &frame, span) {
            Some(value) => Extraction::metres(value).located(Some(bar.center)),
            None => Extraction::unknown("no side wall found beside the water closet"),
        },
        Ok(_) => Extraction::not_applicable("grab bar is on the other wall"),
        Err(e) => e,
    }
}

fn side_length(ctx: &EvalContext, subject: &Subject) -> Extraction {
    bar_metric(ctx, subject, BarWall::Side, |bar, _, _| Some(long_dimension(bar)))
}

fn side_distance_from_rear_wall(ctx: &EvalContext, subject: &Subject) -> Extraction {
    bar_metric(ctx, subject, BarWall::Side, |_, _, span| Some(span.0.max(0.0)))
}

fn side_extension_from_rear_wall(ctx: &EvalContext, subject: &Subject) -> Extraction {
    bar_metric(ctx, subject, BarWall::Side, |_, _, span| Some(span.1))
}

fn rear_length(ctx: &EvalContext, subject: &Subject) -> Extraction {
    bar_metric(ctx, subject, BarWall::Rear, |bar, _, _| Some(long_dimension(bar)))
}

fn rear_extension_side_wall_side(ctx: &EvalContext, subject: &Subject) -> Extraction {
    bar_metric(ctx, subject, BarWall::Rear, |_, frame, span| frame.centre_x.map(|x| x - span.0))
}

fn rear_extension_open_side(ctx: &EvalContext, subject: &Subject) -> Extraction {
    bar_metric(ctx, subject, BarWall::Rear, |_, frame, span| frame.centre_x.map(|x| span.1 - x))
}

fn grab_bar_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    ctx.object(subject)
        .map(|bar| Extraction::metres(bar.top_height).located(Some(bar.center)))
        .unwrap_or_else(wrong_subject)
}

/// Vertical gaps to objects overlapping the bar in plan; the ceiling and floor bound them.
fn vertical_gaps(room: &Room, bar: &Object) -> (f64, f64) {
    let (bottom, top) = vertical_extent(bar);
    let zone = bar.footprint().grown(0.05);
    let others = room.objects.iter().filter(|o| o.id != bar.id && o.footprint().overlaps(&zone));
    others.fold((room.ceiling_height - top, bottom), |(above, below), o| {
        let (ob, ot) = vertical_extent(o);
        let above = if ob >= top { above.min(ob - top) } else { above };
        let below = if ot <= bottom { below.min(bottom - ot) } else { below };
        (above, below)
    })
}

fn grab_bar_clearance_above(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object_in_room(ctx, subject).map(|(room, bar)| Extraction::metres(vertical_gaps(room, bar).0)).unwrap_or_else(|e| e)
}

fn grab_bar_clearance_below(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object_in_room(ctx, subject).map(|(room, bar)| Extraction::metres(vertical_gaps(room, bar).1)).unwrap_or_else(|e| e)
}

fn bar_present(ctx: &EvalContext, subject: &Subject, wall: BarWall) -> Extraction {
    let (room, wc, frame) = match water_closet(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let near = objects_of(room, &["grab_bar"]).filter(|b| b.center.plan().distance(wc.center.plan()) < 1.2);
    let found = near.into_iter().any(|bar| {
        let local = frame.local(bar.center.plan());
        let along_facing = long_axis(bar).dot(frame.facing).abs() > 0.7;
        match wall {
            BarWall::Side => along_facing && local.x < NEAR_WALL,
            BarWall::Rear => !along_facing && local.y < NEAR_WALL,
        }
    });
    if found {
        Extraction::boolean(true)
    } else {
        Extraction::unknown("no grab bar detected; the scan may miss them, so a photo confirms")
    }
}

fn grab_bar_present_side(ctx: &EvalContext, subject: &Subject) -> Extraction {
    bar_present(ctx, subject, BarWall::Side)
}

fn grab_bar_present_rear(ctx: &EvalContext, subject: &Subject) -> Extraction {
    bar_present(ctx, subject, BarWall::Rear)
}

fn nearest_wc(room: &Room, point: Vec2) -> Option<&Object> {
    objects_of(room, WATER_CLOSETS)
        .min_by(|a, b| a.center.plan().distance(point).total_cmp(&b.center.plan().distance(point)))
}

fn dispenser_from_wc_front(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, dispenser) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(wc) = nearest_wc(room, dispenser.center.plan()) else {
        return Extraction::not_applicable("no water closet in the room");
    };
    let Some(frame) = WcFrame::of(room, wc) else {
        return Extraction::unknown("no walls captured around the water closet");
    };
    let front = projected_span(&wc.footprint(), frame.rear_origin, frame.facing).1;
    Extraction::metres(frame.local(dispenser.center.plan()).y - front).located(Some(dispenser.center))
}

fn dispenser_outlet_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    ctx.object(subject)
        .map(|d| Extraction::metres_range(d.bottom_height(), d.center.y).located(Some(d.center)))
        .unwrap_or_else(wrong_subject)
}

/// Compartment size across (perpendicular to the side walls) and front to back of its water closet.
fn compartment_size(ctx: &EvalContext, subject: &Subject) -> Result<(f64, f64), Extraction> {
    let (room, compartment) = object_in_room(ctx, subject)?;
    let footprint = compartment.footprint();
    let wc = objects_of(room, WATER_CLOSETS).find(|wc| footprint.contains(wc.center.plan()));
    let Some(frame) = wc.and_then(|wc| WcFrame::of(room, wc)) else {
        return Ok((compartment.size.x, compartment.size.z));
    };
    let across = projected_span(&footprint, frame.rear_origin, frame.lateral);
    let deep = projected_span(&footprint, frame.rear_origin, frame.facing);
    Ok((across.1 - across.0, deep.1 - deep.0))
}

fn compartment_width(ctx: &EvalContext, subject: &Subject) -> Extraction {
    compartment_size(ctx, subject).map(|(w, _)| Extraction::metres(w)).unwrap_or_else(|e| e)
}

fn compartment_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    compartment_size(ctx, subject).map(|(_, d)| Extraction::metres(d)).unwrap_or_else(|e| e)
}

fn kind_for_width(width: f64) -> &'static str {
    match width {
        w if w >= inches(60.0) - 0.01 => "wheelchair",
        w if (inches(35.0) - 0.01..=inches(37.0) + 0.01).contains(&w) => "ambulatory",
        _ => "other",
    }
}

fn compartment_kind(ctx: &EvalContext, subject: &Subject) -> Extraction {
    compartment_size(ctx, subject).map(|(width, _)| Extraction::text(kind_for_width(width))).unwrap_or_else(|e| e)
}

/// The compartment around a water closet, sized in that water closet's frame.
fn wc_compartment_kind(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, wc, frame) = match water_closet(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let compartment = objects_of(room, &["toilet_compartment"]).find(|c| c.footprint().contains(wc.center.plan()));
    match compartment {
        None => Extraction::text("none"),
        Some(c) => {
            let across = projected_span(&c.footprint(), frame.rear_origin, frame.lateral);
            Extraction::text(kind_for_width(across.1 - across.0))
        }
    }
}

/// Depth inside the compartment from the front of the water closet to the compartment front.
fn compartment_front_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, compartment) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let footprint = compartment.footprint();
    let Some(wc) = objects_of(room, WATER_CLOSETS).find(|wc| footprint.contains(wc.center.plan())) else {
        return Extraction::unknown("no water closet found inside the compartment");
    };
    let Some(frame) = WcFrame::of(room, wc) else {
        return Extraction::unknown("no walls captured around the water closet");
    };
    let wc_front = projected_span(&wc.footprint(), frame.rear_origin, frame.facing).1;
    let compartment_front = projected_span(&footprint, frame.rear_origin, frame.facing).1;
    Extraction::metres((compartment_front - wc_front).max(0.0)).located(Some(compartment.center))
}

/// Below the side grab bar with 1.5 in between, and not past the bar's ends.
fn dispenser_below_grab_bar(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, dispenser) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let bar = objects_of(room, &["grab_bar"])
        .filter(|b| b.footprint().distance_to(dispenser.center.plan()) < 0.3)
        .min_by(|a, b| {
            a.footprint()
                .distance_to(dispenser.center.plan())
                .total_cmp(&b.footprint().distance_to(dispenser.center.plan()))
        });
    let Some(bar) = bar else {
        return Extraction::unknown("no grab bar detected near the dispenser; a photo confirms");
    };
    let gap = bar.bottom_height() - dispenser.top_height;
    let along = projected_span(&bar.footprint(), bar.center.plan(), long_axis(bar));
    let offset = (dispenser.center.plan() - bar.center.plan()).dot(long_axis(bar));
    Extraction::boolean(gap >= inches(1.5) - 1e-6 && offset >= along.0 && offset <= along.1)
}

/// A bowl box that stops short of the floor is wall hung.
fn wc_mounting(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let wc = match ctx.object(subject) {
        Some(o) if WATER_CLOSETS.contains(&o.category.as_str()) => Some(o),
        Some(_) => None,
        None => None,
    };
    let wc = wc.or_else(|| {
        let (room, compartment) = object_in_room(ctx, subject).ok()?;
        objects_of(room, WATER_CLOSETS).find(|w| compartment.footprint().contains(w.center.plan()))
    });
    match wc {
        Some(w) => Extraction::text(if w.bottom_height() > 0.1 { "wall_hung" } else { "floor_mounted" }),
        None => Extraction::unknown("no water closet found"),
    }
}

fn urinal_rim_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    ctx.object(subject).map(|u| Extraction::metres(short_dimension(u))).unwrap_or_else(wrong_subject)
}

fn lavatory_rim_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    ctx.object(subject).map(|l| Extraction::metres(l.top_height).located(Some(l.center))).unwrap_or_else(wrong_subject)
}

fn lavatory_from_wc_centerline(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, lavatory) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(wc) = nearest_wc(room, lavatory.center.plan()) else {
        return Extraction::not_applicable("no water closet in the room");
    };
    let Some(frame) = WcFrame::of(room, wc) else {
        return Extraction::unknown("no walls captured around the water closet");
    };
    let centre_x = frame.local(wc.center.plan()).x;
    let span = projected_span(&lavatory.footprint(), frame.rear_origin, frame.lateral);
    let gap = if span.0 > centre_x {
        span.0 - centre_x
    } else if span.1 < centre_x {
        centre_x - span.1
    } else {
        0.0
    };
    Extraction::metres(gap).located(Some(lavatory.center))
}

fn lavatory_centerline_from_side_wall(ctx: &EvalContext, subject: &Subject) -> Extraction {
    match water_closet(ctx, subject) {
        Ok((_, lavatory, frame)) => match frame.centre_x {
            Some(x) => Extraction::metres(x).located(Some(lavatory.center)),
            None => Extraction::unknown("no side wall found beside the lavatory"),
        },
        Err(e) => e,
    }
}

/// How far the side bar's front end reaches past the front of the water closet.
fn side_bar_beyond_wc(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, bar) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(wc) = nearest_wc(room, bar.center.plan()) else {
        return Extraction::not_applicable("no water closet in the room");
    };
    let front = WcFrame::of(room, wc).map(|frame| projected_span(&wc.footprint(), frame.rear_origin, frame.facing).1);
    bar_metric(ctx, subject, BarWall::Side, |_, _, span| Some(span.1))
        .map_value(|far_end| far_end - front.unwrap_or(far_end))
}

/// Free depth in front of the water closet across a 60 in band from the side wall.
fn wc_front_maneuvering_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, wc, frame) = match water_closet(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let front = projected_span(&wc.footprint(), frame.rear_origin, frame.facing).1;
    let points: Vec<Vec2> =
        obstruction_points(room, wc, &frame).into_iter().map(|p| Vec2::new(p.x, p.y - front)).collect();
    let band = if frame.side.is_some() { CLEARANCE_WIDTH } else { f64::INFINITY };
    Extraction::metres(clear_extent(&points, |p| p.y, |p| p.x.abs(), band)).located(Some(wc.center))
}
