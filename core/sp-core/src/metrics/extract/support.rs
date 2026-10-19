//! Helpers shared by extractors.

use crate::geometry::{OrientedBox2, Segment2, Vec2, Vec3};
use crate::metrics::subject::Subject;
use crate::metrics::{EvalContext, Extraction};
use crate::scene::{Object, Room};

pub const WATER_CLOSETS: &[&str] = &["toilet", "water_closet"];
pub const LAVATORIES: &[&str] = &["lavatory", "sink"];
pub const COUNTERS: &[&str] = &["counter", "service_counter", "sales_counter", "checkout_aisle", "bar_counter", "food_service_line"];
pub const DINING_SURFACES: &[&str] = &["dining_table", "bar_counter"];

pub fn wrong_subject() -> Extraction {
    Extraction::not_applicable("metric is not defined for this kind of element")
}

pub fn needs_mesh(_: &EvalContext, _: &Subject) -> Extraction {
    Extraction::unknown("needs the floor mesh height field; scan boxes assume a level floor")
}

pub fn needs_detail(_: &EvalContext, _: &Subject) -> Extraction {
    Extraction::unknown("needs a photo or tape measurement; the scan box does not resolve this detail")
}

pub fn floor_point(p: Vec2) -> Option<Vec3> {
    Some(Vec3::new(p.x, 0.0, p.y))
}

/// The subject's object and room, or the extraction to return when the subject is not an object.
pub fn object_in_room<'a>(ctx: &EvalContext<'a>, subject: &Subject) -> Result<(&'a Room, &'a Object), Extraction> {
    match (ctx.room(subject), ctx.object(subject)) {
        (Some(room), Some(object)) => Ok((room, object)),
        _ => Err(wrong_subject()),
    }
}

pub fn vertical_extent(object: &Object) -> (f64, f64) {
    let bottom = object.bottom_height();
    (bottom, object.top_height.max(bottom))
}

/// The value is some height within the object's box.
pub fn within_box_height(object: &Object) -> Extraction {
    let (bottom, top) = vertical_extent(object);
    Extraction::metres_range(bottom, top).located(Some(object.center))
}

pub fn long_dimension(object: &Object) -> f64 {
    object.size.x.max(object.size.z)
}

pub fn short_dimension(object: &Object) -> f64 {
    object.size.x.min(object.size.z)
}

/// Unit vector along the object's longer horizontal side.
pub fn long_axis(object: &Object) -> Vec2 {
    let (x_axis, z_axis) = object.footprint().axes();
    if object.size.x >= object.size.z { x_axis } else { z_axis }
}

/// Wall segments, or the floor outline when no walls were captured.
pub fn boundary_segments(room: &Room) -> Vec<Segment2> {
    if room.walls.is_empty() { room.floor.edges().collect() } else { room.walls.iter().map(|w| w.segment()).collect() }
}

pub fn nearest_boundary(room: &Room, point: Vec2) -> Option<Segment2> {
    boundary_segments(room).into_iter().min_by(|a, b| a.distance_to(point).total_cmp(&b.distance_to(point)))
}

pub fn objects_of<'a>(room: &'a Room, categories: &'a [&'a str]) -> impl Iterator<Item = &'a Object> + 'a {
    room.objects.iter().filter(move |o| categories.contains(&o.category.as_str()))
}

/// The object this one sits on (a counter under a card reader), if any.
pub fn supporting_object<'a>(room: &'a Room, object: &Object) -> Option<&'a Object> {
    let bottom = object.bottom_height();
    room.objects.iter().find(|other| {
        other.id != object.id && (other.top_height - bottom).abs() < 0.1 && other.footprint().contains(object.center.plan()) && bottom > 0.2
    })
}

/// Objects resting on top of `surface`.
pub fn items_on<'a>(room: &'a Room, surface: &'a Object) -> impl Iterator<Item = &'a Object> + 'a {
    room.objects.iter().filter(move |o| {
        o.id != surface.id && (o.bottom_height() - surface.top_height).abs() < 0.1 && surface.footprint().contains(o.center.plan())
    })
}

/// Extent of `footprint` projected on `axis`, as (min, max) relative to `origin`.
pub fn projected_span(footprint: &OrientedBox2, origin: Vec2, axis: Vec2) -> (f64, f64) {
    footprint.corners().iter().map(|c| (*c - origin).dot(axis)).fold((f64::INFINITY, f64::NEG_INFINITY), |(lo, hi), v| (lo.min(v), hi.max(v)))
}

/// Objects whose footprints touch `object`'s within `gap` metres.
pub fn adjoining<'a>(room: &'a Room, object: &'a Object, categories: &'a [&'a str], gap: f64) -> impl Iterator<Item = &'a Object> + 'a {
    let grown = object.footprint().grown(gap);
    objects_of(room, categories).filter(move |o| o.id != object.id && o.footprint().overlaps(&grown))
}
