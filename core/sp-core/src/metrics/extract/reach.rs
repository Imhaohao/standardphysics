//! Operable parts and reach ranges (308, 309), protruding objects (307) and mounted accessories.

use super::clear_floor::front_face;
use super::support::{LAVATORIES, needs_detail, nearest_boundary, object_in_room, supporting_object, vertical_extent, within_box_height, wrong_subject};
use crate::metrics::subject::Subject;
use crate::metrics::{EvalContext, Extraction, Extractor};
use crate::scene::{Object, Room};
use crate::units::inches;

pub const EXTRACTORS: &[(&str, Extractor)] = &[
    ("operable_part.height", operable_height),
    ("operable_part.low_height", operable_low_height),
    ("reach.high_forward_unobstructed", unobstructed_reach),
    ("reach.high_side_unobstructed", unobstructed_reach),
    ("reach.high_forward_obstructed", obstructed_reach),
    ("reach.high_side_obstructed", obstructed_reach),
    ("reach.obstruction_depth", obstruction_depth),
    ("reach.obstruction_height", obstruction_height),
    ("protrusion.leading_edge_height", leading_edge_height),
    ("protrusion.depth_between_27_80", protrusion_depth),
    ("protrusion.post_mounted_overhang", needs_detail),
    ("protrusion.between_posts_clear_distance", needs_detail),
    ("protrusion.between_posts_lowest_edge", needs_detail),
    ("kiosk.display_height", box_height),
    ("telephone.operable_part_height", box_height),
    ("coat_hook.height", box_height),
    ("toilet_room.accessory_operable_height", box_height),
    ("shelf.highest_shelf_used_height", highest_shelf),
    ("shelf.lowest_shelf_used_height", lowest_shelf),
    ("mirror.reflecting_surface_bottom_height", mirror_bottom),
    ("mirror.above_lavatory", mirror_above_lavatory),
];

const SHELVING: &[&str] = &["shelf", "self_service_shelf", "storage", "display_rack", "food_service_line"];
/// The lowest shelf of a unit sits within this height of its base.
const LOWEST_SHELF_BAND: f64 = 0.35;
/// The highest shelf surface sits at most this far below the top of the unit.
const TOP_SHELF_BAND: f64 = 0.05;

fn object<'a>(ctx: &EvalContext<'a>, subject: &Subject) -> Result<&'a Object, Extraction> {
    ctx.object(subject).ok_or_else(wrong_subject)
}

/// Height of the highest operable part: somewhere within the box, except where the element's
/// shape says more (faucets sit just above a lavatory rim, the top shelf at the top of shelving).
fn highest_operable(object: &Object) -> Extraction {
    let (bottom, top) = vertical_extent(object);
    let category = object.category.as_str();
    if LAVATORIES.contains(&category) {
        return Extraction::metres_range(top, top + 0.2).located(Some(object.center));
    }
    if SHELVING.contains(&category) {
        return Extraction::metres_range((top - TOP_SHELF_BAND).max(bottom), top).located(Some(object.center));
    }
    within_box_height(object)
}

fn operable_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    match object(ctx, subject) {
        Ok(o) if matches!(o.category.as_str(), "toilet" | "water_closet" | "urinal") => needs_detail(ctx, subject),
        Ok(o) => highest_operable(o),
        Err(e) => e,
    }
}

fn operable_low_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    match object(ctx, subject) {
        Ok(o) if SHELVING.contains(&o.category.as_str()) => lowest_shelf_range(o),
        Ok(o) => within_box_height(o),
        Err(e) => e,
    }
}

fn lowest_shelf_range(object: &Object) -> Extraction {
    let (bottom, top) = vertical_extent(object);
    Extraction::metres_range(bottom, top.min(bottom + LOWEST_SHELF_BAND)).located(Some(object.center))
}

/// Reaching over something (a counter under a card reader) or not.
fn obstruction<'a>(room: &'a Room, object: &Object) -> Option<&'a Object> {
    supporting_object(room, object)
}

fn unobstructed_reach(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, object) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    if obstruction(room, object).is_some() {
        return Extraction::not_applicable("reached over an obstruction");
    }
    operable_height(ctx, subject)
}

fn obstructed_reach(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, object) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    match obstruction(room, object) {
        Some(_) => operable_height(ctx, subject),
        None => Extraction::not_applicable("nothing to reach over"),
    }
}

/// Distance from the obstruction's front edge back to the operable part.
fn obstruction_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, object) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let Some(below) = obstruction(room, object) else { return Extraction::not_applicable("nothing to reach over") };
    let Some(analysis) = ctx.analysis(room.storey) else { return Extraction::unknown("storey not analysed") };
    let face = front_face(&analysis.grid, &below.footprint());
    let depth = (face.centre - object.center.plan()).dot(face.outward).max(0.0);
    Extraction::metres(depth).located(Some(object.center))
}

fn obstruction_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, object) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    match obstruction(room, object) {
        Some(below) => Extraction::metres(below.top_height),
        None => Extraction::not_applicable("nothing to reach over"),
    }
}

fn leading_edge_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(|o| Extraction::metres(o.bottom_height()).located(Some(o.center))).unwrap_or_else(|e| e)
}

/// How far an object with its leading edge between 27 and 80 in sticks out from the wall behind it.
fn protrusion_depth(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, object) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let bottom = object.bottom_height();
    if bottom <= inches(27.0) {
        return Extraction::not_applicable("leading edge at or below 27 in is detectable by cane");
    }
    if bottom > inches(80.0) {
        return Extraction::not_applicable("leading edge is above 80 in");
    }
    let Some(wall) = nearest_boundary(room, object.center.plan()) else { return Extraction::unknown("no wall captured") };
    let projection = object.footprint().corners().iter().map(|c| wall.distance_to(*c)).fold(0.0, f64::max);
    Extraction::metres(projection).located(Some(object.center))
}

fn box_height(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(within_box_height).unwrap_or_else(|e| e)
}

fn highest_shelf(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject)
        .map(|o| {
            let (bottom, top) = vertical_extent(o);
            Extraction::metres_range((top - TOP_SHELF_BAND).max(bottom), top).located(Some(o.center))
        })
        .unwrap_or_else(|e| e)
}

fn lowest_shelf(ctx: &EvalContext, subject: &Subject) -> Extraction {
    object(ctx, subject).map(lowest_shelf_range).unwrap_or_else(|e| e)
}

fn mirror_bottom(ctx: &EvalContext, subject: &Subject) -> Extraction {
    leading_edge_height(ctx, subject)
}

fn mirror_above_lavatory(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let (room, mirror) = match object_in_room(ctx, subject) {
        Ok(found) => found,
        Err(e) => return e,
    };
    let below = room.objects.iter().filter(|o| matches!(o.category.as_str(), "lavatory" | "sink" | "counter"));
    let above = below.into_iter().any(|o| o.footprint().distance_to(mirror.center.plan()) < 0.3 && o.top_height <= mirror.bottom_height() + 0.05);
    Extraction::boolean(above)
}
