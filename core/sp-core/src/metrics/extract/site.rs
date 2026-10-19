//! Whole-facility counts. Counts of *accessible* elements read the outcomes of rules already
//! evaluated for those elements, so the site subject is evaluated last.

use super::support::{DINING_SURFACES, vertical_extent, wrong_subject};
use crate::metrics::subject::{Subject, SubjectRef};
use crate::metrics::{EvalContext, Extraction, Extractor, SubjectOutcome};
use crate::scene::RoomKind;
use crate::units::inches;

pub const EXTRACTORS: &[(&str, Extractor)] = &[
    ("site.public_entrances_total", public_entrances_total),
    ("site.public_entrances_accessible", public_entrances_accessible),
    ("site.has_exterior_route_scanned", has_exterior_route_scanned),
    ("site.dining_seating_count", dining_seating_count),
    ("site.dining_surfaces_total", dining_surfaces_total),
    ("site.dining_surfaces_accessible", dining_surfaces_accessible),
    ("site.dining_areas_with_accessible_surface_ratio", dining_areas_ratio),
    ("site.toilet_rooms_public_total", toilet_rooms_total),
    ("site.checkout_aisles_total", checkout_aisles_total),
    ("site.checkout_aisles_accessible", checkout_aisles_accessible),
    ("site.has_multiple_stories_public", has_multiple_stories),
    ("site.has_elevator", has_elevator),
    ("site.has_fitting_rooms", has_fitting_rooms),
    ("site.has_atm_or_depository", has_atm_or_depository),
    ("drinking_fountain.count_wheelchair", fountains_for_wheelchair),
    ("drinking_fountain.count_standing", fountains_for_standing),
];

const SEATS: &[&str] = &["chair", "bench", "sofa"];
const CHECKOUTS: &[&str] = &["checkout_aisle"];
const FOUNTAINS: &[&str] = &["drinking_fountain", "bottle_filler"];

fn site_only(subject: &Subject) -> Result<(), Extraction> {
    if subject.reference == SubjectRef::Site { Ok(()) } else { Err(wrong_subject()) }
}

fn entrance_ids<'a>(ctx: &EvalContext<'a>) -> Vec<&'a str> {
    ctx.scene
        .rooms
        .iter()
        .flat_map(|r| &r.openings)
        .filter(|o| o.kind.is_passable() && !ctx.scene.is_interior_opening(&o.id))
        .map(|o| o.id.as_str())
        .collect()
}

fn public_entrances_total(ctx: &EvalContext, subject: &Subject) -> Extraction {
    site_only(subject).map(|_| Extraction::count(entrance_ids(ctx).len())).unwrap_or_else(|e| e)
}

/// Lower bound: elements whose rules all ran and none failed with at least one pass. Upper bound:
/// elements with no failure.
fn accessible_count<'a>(ctx: &EvalContext, ids: impl Iterator<Item = &'a str>) -> Extraction {
    let Some(_) = ctx.outcomes else {
        return Extraction::unknown("counted after the element rules are evaluated");
    };
    let outcomes: Vec<SubjectOutcome> = ids.map(|id| ctx.outcome(id).unwrap_or_default()).collect();
    let surely = outcomes.iter().filter(|o| o.any_pass && !o.any_fail && !o.any_unresolved).count();
    let possibly = outcomes.iter().filter(|o| !o.any_fail).count();
    Extraction::count_range(surely, possibly)
}

fn public_entrances_accessible(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if let Err(e) = site_only(subject) {
        return e;
    }
    accessible_count(ctx, entrance_ids(ctx).into_iter())
}

fn has_exterior_route_scanned(_: &EvalContext, subject: &Subject) -> Extraction {
    site_only(subject)
        .map(|_| Extraction::boolean(false).noted("the scene model captures interior rooms only"))
        .unwrap_or_else(|e| e)
}

fn dining_seating_count(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if let Err(e) = site_only(subject) {
        return e;
    }
    let seats = ctx.objects_of(SEATS).filter(|(room, seat)| {
        super::support::objects_of(room, DINING_SURFACES).any(|table| table.footprint().distance_to(seat.center.plan()) < 0.75)
    });
    Extraction::count(seats.count())
}

fn dining_surfaces_total(ctx: &EvalContext, subject: &Subject) -> Extraction {
    site_only(subject).map(|_| Extraction::count(ctx.objects_of(DINING_SURFACES).count())).unwrap_or_else(|e| e)
}

fn dining_surfaces_accessible(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if let Err(e) = site_only(subject) {
        return e;
    }
    accessible_count(ctx, ctx.objects_of(DINING_SURFACES).map(|(_, o)| o.id.as_str()))
}

fn dining_areas_ratio(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if let Err(e) = site_only(subject) {
        return e;
    }
    if ctx.outcomes.is_none() {
        return Extraction::unknown("counted after the element rules are evaluated");
    }
    let areas: Vec<(bool, bool)> = ctx
        .scene
        .rooms
        .iter()
        .filter(|r| super::support::objects_of(r, DINING_SURFACES).next().is_some())
        .map(|r| {
            let outcomes: Vec<SubjectOutcome> = super::support::objects_of(r, DINING_SURFACES).map(|o| ctx.outcome(&o.id).unwrap_or_default()).collect();
            (outcomes.iter().any(|o| o.any_pass && !o.any_fail && !o.any_unresolved), outcomes.iter().any(|o| !o.any_fail))
        })
        .collect();
    if areas.is_empty() {
        return Extraction::not_applicable("no dining surfaces in the scan");
    }
    let n = areas.len() as f64;
    let surely = areas.iter().filter(|a| a.0).count() as f64 / n;
    let possibly = areas.iter().filter(|a| a.1).count() as f64 / n;
    Extraction::Measured(crate::metrics::Measurement::geometry(crate::metrics::Value::range(surely, possibly), crate::units::Unit::Ratio))
}

fn toilet_rooms_total(ctx: &EvalContext, subject: &Subject) -> Extraction {
    let count = ctx.scene.rooms.iter().filter(|r| r.kind == RoomKind::Restroom).count();
    site_only(subject).map(|_| Extraction::count(count)).unwrap_or_else(|e| e)
}

fn checkout_aisles_total(ctx: &EvalContext, subject: &Subject) -> Extraction {
    site_only(subject).map(|_| Extraction::count(ctx.objects_of(CHECKOUTS).count())).unwrap_or_else(|e| e)
}

fn checkout_aisles_accessible(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if let Err(e) = site_only(subject) {
        return e;
    }
    accessible_count(ctx, ctx.objects_of(CHECKOUTS).map(|(_, o)| o.id.as_str()))
}

/// Presence confirmed by the scan when found; absence is not proof (the owner answers).
fn present_or_unknown(ctx: &EvalContext, subject: &Subject, categories: &'static [&'static str]) -> Extraction {
    if let Err(e) = site_only(subject) {
        return e;
    }
    if ctx.objects_of(categories).next().is_some() {
        Extraction::boolean(true)
    } else {
        Extraction::unknown("not seen in the scan; the owner confirms")
    }
}

fn has_multiple_stories(ctx: &EvalContext, subject: &Subject) -> Extraction {
    if let Err(e) = site_only(subject) {
        return e;
    }
    if ctx.scene.storeys().len() > 1 { Extraction::boolean(true) } else { Extraction::unknown("one storey scanned; the owner confirms") }
}

fn has_elevator(ctx: &EvalContext, subject: &Subject) -> Extraction {
    present_or_unknown(ctx, subject, &["elevator", "platform_lift"])
}

fn has_fitting_rooms(ctx: &EvalContext, subject: &Subject) -> Extraction {
    present_or_unknown(ctx, subject, &["fitting_room"])
}

fn has_atm_or_depository(ctx: &EvalContext, subject: &Subject) -> Extraction {
    present_or_unknown(ctx, subject, &["atm", "depository"])
}

/// Count fountains whose spout (somewhere in the box's upper part) is surely / possibly in `lo..=hi`.
fn fountains_in_band(ctx: &EvalContext, subject: &Subject, lo: f64, hi: f64) -> Extraction {
    if let Err(e) = site_only(subject) {
        return e;
    }
    let spans: Vec<(f64, f64)> = ctx.objects_of(FOUNTAINS).map(|(_, o)| vertical_extent(o)).collect();
    let surely = spans.iter().filter(|(b, t)| *b >= lo && *t <= hi).count();
    let possibly = spans.iter().filter(|(b, t)| *t >= lo && *b <= hi).count();
    Extraction::count_range(surely, possibly)
}

fn fountains_for_wheelchair(ctx: &EvalContext, subject: &Subject) -> Extraction {
    fountains_in_band(ctx, subject, 0.0, inches(36.0))
}

fn fountains_for_standing(ctx: &EvalContext, subject: &Subject) -> Extraction {
    fountains_in_band(ctx, subject, inches(38.0), inches(43.0))
}
