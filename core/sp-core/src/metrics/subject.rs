//! Everything a rule can be evaluated against, with the tags `applies_to` matches.

use super::Catalog;
use crate::analysis::{Destination, StoreyAnalysis};
use crate::geometry::Vec3;
use crate::scene::{OpeningKind, RoomKind, Scene};
use std::collections::{BTreeSet, HashMap};

pub const SITE_ID: &str = "site";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SubjectRef {
    Site,
    Room { room: usize },
    Floor { room: usize },
    Wall { room: usize, wall: usize },
    Opening { room: usize, opening: usize },
    Object { room: usize, object: usize },
    Route { storey: i32, route: usize },
}

#[derive(Debug, Clone, PartialEq)]
pub struct Subject {
    pub id: String,
    pub reference: SubjectRef,
    pub tags: BTreeSet<String>,
    pub room_id: Option<String>,
    pub storey: i32,
    pub location: Option<Vec3>,
}

impl Subject {
    pub fn has_tag(&self, tag: &str) -> bool {
        self.tags.contains(tag)
    }
}

/// Tag sets derived from the catalog once.
pub struct Tagging {
    clear_floor_space: BTreeSet<String>,
    operable_part: BTreeSet<String>,
    canonical: HashMap<String, String>,
}

impl Tagging {
    pub fn from_catalog(catalog: &Catalog) -> Self {
        let canonical = catalog
            .object_categories
            .iter()
            .filter_map(|c| c.canonical.as_ref().filter(|canon| **canon != c.id).map(|canon| (c.id.clone(), canon.clone())))
            .collect();
        Self {
            clear_floor_space: catalog.categories_for_element("clear_floor_space"),
            operable_part: catalog.categories_for_element("operable_part"),
            canonical,
        }
    }

    fn object_tags(&self, category: &str) -> BTreeSet<String> {
        let mut tags = BTreeSet::from([category.to_string(), "object".to_string()]);
        if let Some(canonical) = self.canonical.get(category) {
            tags.insert(canonical.clone());
        }
        let has = |set: &BTreeSet<String>| tags.iter().any(|t| set.contains(t));
        if has(&self.clear_floor_space) {
            tags.insert("clear_floor_space".into());
        }
        if has(&self.operable_part) {
            tags.insert("operable_part".into());
        }
        tags
    }
}

fn tags<const N: usize>(items: [&str; N]) -> BTreeSet<String> {
    items.iter().map(|s| s.to_string()).collect()
}

/// Every subject in the scene: the site, rooms, floors, walls, openings, objects and route legs.
pub fn enumerate_subjects(scene: &Scene, analyses: &HashMap<i32, StoreyAnalysis>, tagging: &Tagging) -> Vec<Subject> {
    let mut subjects = vec![site_subject()];
    for room_index in 0..scene.rooms.len() {
        subjects.extend(room_subjects(scene, room_index, tagging));
    }
    let mut storeys: Vec<&i32> = analyses.keys().collect();
    storeys.sort();
    for storey in storeys {
        subjects.extend(route_subjects(scene, &analyses[storey]));
    }
    subjects
}

pub fn site_subject() -> Subject {
    Subject { id: SITE_ID.into(), reference: SubjectRef::Site, tags: tags(["site"]), room_id: None, storey: 0, location: None }
}

/// The room, its floor, walls, openings and objects.
pub fn room_subjects(scene: &Scene, room_index: usize, tagging: &Tagging) -> Vec<Subject> {
    let room = &scene.rooms[room_index];
    let make = |id: String, reference, tags, location| Subject { id, reference, tags, room_id: Some(room.id.clone()), storey: room.storey, location };
    let centre = room.floor.centroid();
    let centre = Some(Vec3::new(centre.x, 0.0, centre.y));
    let mut room_tags = tags(["room", room.kind.as_str()]);
    if room.kind == RoomKind::Restroom {
        room_tags.insert("toilet_room".into());
    }
    let mut out = vec![
        make(room.id.clone(), SubjectRef::Room { room: room_index }, room_tags, centre),
        make(format!("floor:{}", room.id), SubjectRef::Floor { room: room_index }, tags(["floor"]), centre),
    ];
    out.extend(room.walls.iter().enumerate().map(|(i, w)| {
        let mid = w.segment().midpoint();
        make(w.id.clone(), SubjectRef::Wall { room: room_index, wall: i }, tags(["wall"]), Some(Vec3::new(mid.x, 0.0, mid.y)))
    }));
    out.extend(room.openings.iter().enumerate().map(|(i, o)| {
        make(o.id.clone(), SubjectRef::Opening { room: room_index, opening: i }, opening_tags(scene, o), Some(o.center))
    }));
    out.extend(room.objects.iter().enumerate().map(|(i, o)| {
        make(o.id.clone(), SubjectRef::Object { room: room_index, object: i }, tagging.object_tags(&o.category), Some(o.center))
    }));
    out
}

fn opening_tags(scene: &Scene, opening: &crate::scene::Opening) -> BTreeSet<String> {
    let mut set = tags([match opening.kind {
        OpeningKind::Door => "door",
        OpeningKind::Opening => "doorway",
        OpeningKind::Window => "window",
    }]);
    if opening.kind.is_passable() && !scene.is_interior_opening(&opening.id) {
        set.insert("entrance".into());
    }
    set
}

pub fn route_subjects(scene: &Scene, analysis: &StoreyAnalysis) -> Vec<Subject> {
    analysis
        .routes
        .iter()
        .enumerate()
        .map(|(i, record)| Subject {
            id: record.id.clone(),
            reference: SubjectRef::Route { storey: analysis.storey, route: i },
            tags: tags(["route"]),
            room_id: destination_room(scene, &record.destination),
            storey: analysis.storey,
            location: record.leg.as_ref().and_then(|leg| leg.points.last()).map(|p| Vec3::new(p.x, 0.0, p.y)),
        })
        .collect()
}

fn destination_room(scene: &Scene, destination: &Destination) -> Option<String> {
    let id = destination.id();
    scene
        .rooms
        .iter()
        .find(|r| r.id == id || r.openings.iter().any(|o| o.id == id) || r.objects.iter().any(|o| o.id == id))
        .map(|r| r.id.clone())
}
