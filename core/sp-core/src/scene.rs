//! The Scene contract shared with the server, web (via JSON Schema) and iOS (via UniFFI).
//! Units: metres and radians, right-handed, Y up, floor at y = 0 for each storey.

use crate::geometry::{OrientedBox2, Polygon2, Segment2, Vec2, Vec3};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const SCENE_VERSION: u32 = 2;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Scene {
    pub version: u32,
    #[serde(default)]
    pub rooms: Vec<Room>,
    #[serde(default)]
    pub connections: Vec<RoomConnection>,
    #[serde(default)]
    pub observations: Vec<Observation>,
}

impl Default for Scene {
    fn default() -> Self {
        Self { version: SCENE_VERSION, rooms: Vec::new(), connections: Vec::new(), observations: Vec::new() }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum RoomKind {
    Shop,
    Restaurant,
    Restroom,
    Office,
    Corridor,
    Kitchen,
    Storage,
    #[default]
    Other,
}

impl RoomKind {
    pub fn as_str(self) -> &'static str {
        match self {
            RoomKind::Shop => "shop",
            RoomKind::Restaurant => "restaurant",
            RoomKind::Restroom => "restroom",
            RoomKind::Office => "office",
            RoomKind::Corridor => "corridor",
            RoomKind::Kitchen => "kitchen",
            RoomKind::Storage => "storage",
            RoomKind::Other => "other",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Room {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub kind: RoomKind,
    /// Storey index; rooms sharing a storey share one floor plane and one occupancy grid.
    #[serde(default)]
    pub storey: i32,
    /// Floor outline in plan (x = world X, y = world Z).
    pub floor: Polygon2,
    pub ceiling_height: f64,
    #[serde(default)]
    pub walls: Vec<Wall>,
    #[serde(default)]
    pub openings: Vec<Opening>,
    #[serde(default)]
    pub objects: Vec<Object>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Wall {
    pub id: String,
    pub start: Vec2,
    pub end: Vec2,
    pub height: f64,
    #[serde(default = "default_wall_thickness")]
    pub thickness: f64,
}

pub fn default_wall_thickness() -> f64 {
    0.1
}

impl Wall {
    pub fn segment(&self) -> Segment2 {
        Segment2::new(self.start, self.end)
    }

    pub fn length(&self) -> f64 {
        self.segment().length()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum OpeningKind {
    Door,
    Window,
    Opening,
}

impl OpeningKind {
    pub fn as_str(self) -> &'static str {
        match self {
            OpeningKind::Door => "door",
            OpeningKind::Window => "window",
            OpeningKind::Opening => "opening",
        }
    }

    /// Doors and cased openings can be walked through; windows cannot.
    pub fn is_passable(self) -> bool {
        !matches!(self, OpeningKind::Window)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct DoorSwing {
    /// Hinge side as seen from the side the door swings into.
    pub hinge: HingeSide,
    /// True when the door swings into this room.
    pub swings_in: bool,
    /// Leaf count (1 or 2).
    #[serde(default = "one")]
    pub leaves: u32,
}

fn one() -> u32 {
    1
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum HingeSide {
    Left,
    Right,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Opening {
    pub id: String,
    pub kind: OpeningKind,
    pub wall_id: String,
    /// Centre of the opening; `y` is the height of its middle above the floor.
    pub center: Vec3,
    pub width: f64,
    pub height: f64,
    #[serde(default)]
    pub swing: Option<DoorSwing>,
    #[serde(default)]
    pub hardware: Option<String>,
}

impl Opening {
    pub fn bottom_height(&self) -> f64 {
        self.center.y - self.height / 2.0
    }

    pub fn top_height(&self) -> f64 {
        self.center.y + self.height / 2.0
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ObjectSource {
    #[default]
    Roomplan,
    Detector,
    Mesh,
    Owner,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Object {
    pub id: String,
    /// Category from `rules/metrics.json` `object_categories`.
    pub category: String,
    /// Centre of the bounding box; `y` is height above the floor.
    pub center: Vec3,
    /// Box size (width along local X, height, depth along local Z).
    pub size: Vec3,
    pub yaw: f64,
    /// Height of the top surface above the floor (usually `center.y + size.y / 2`).
    pub top_height: f64,
    #[serde(default = "full_confidence")]
    pub confidence: f64,
    #[serde(default)]
    pub source: ObjectSource,
    #[serde(default)]
    pub attributes: BTreeMap<String, String>,
}

fn full_confidence() -> f64 {
    1.0
}

impl Object {
    pub fn footprint(&self) -> OrientedBox2 {
        OrientedBox2::new(self.center.plan(), self.size.x, self.size.z, self.yaw)
    }

    pub fn bottom_height(&self) -> f64 {
        (self.center.y - self.size.y / 2.0).max(0.0)
    }

    /// Plan direction the object's front faces (its local +Z axis).
    pub fn facing(&self) -> Vec2 {
        crate::geometry::yaw_axes(self.yaw).1
    }

    pub fn attribute(&self, key: &str) -> Option<&str> {
        self.attributes.get(key).map(String::as_str)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct RoomConnection {
    pub from_room: String,
    pub to_room: String,
    /// The door or opening shared by both rooms, when known.
    #[serde(default)]
    pub opening_id: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ObservationSource {
    Measured,
    Photo,
    Owner,
}

/// Value of an observation: a number (with `unit`), a yes/no answer, or text.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(untagged)]
pub enum ObservationValue {
    Bool(bool),
    Number(f64),
    Text(String),
}

/// A fact that cannot be derived from boxes: sign text, Braille present, door opening force reported
/// by the owner, a tape-measured height.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Observation {
    pub id: String,
    pub subject_id: String,
    pub metric: String,
    pub value: ObservationValue,
    #[serde(default)]
    pub unit: Option<String>,
    pub source: ObservationSource,
    #[serde(default = "full_confidence")]
    pub confidence: f64,
}

impl Scene {
    pub fn room(&self, id: &str) -> Option<&Room> {
        self.rooms.iter().find(|r| r.id == id)
    }

    pub fn storeys(&self) -> Vec<i32> {
        let mut storeys: Vec<i32> = self.rooms.iter().map(|r| r.storey).collect();
        storeys.sort_unstable();
        storeys.dedup();
        storeys
    }

    pub fn rooms_on(&self, storey: i32) -> impl Iterator<Item = &Room> {
        self.rooms.iter().filter(move |r| r.storey == storey)
    }

    /// Replace the room with the same id, or add it. Returns true when it replaced one.
    pub fn upsert_room(&mut self, room: Room) -> bool {
        match self.rooms.iter_mut().find(|r| r.id == room.id) {
            Some(slot) => {
                *slot = room;
                true
            }
            None => {
                self.rooms.push(room);
                false
            }
        }
    }

    /// True when `opening_id` joins two rooms (so it is not an entrance from outside).
    pub fn is_interior_opening(&self, opening_id: &str) -> bool {
        self.connections.iter().any(|c| c.opening_id.as_deref() == Some(opening_id))
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("scene serialises")
    }

    pub fn from_json(json: &str) -> serde_json::Result<Scene> {
        serde_json::from_str(json)
    }
}

/// JSON Schema for [`Scene`], as written to `core/schema/scene.schema.json`.
pub fn scene_json_schema() -> String {
    let schema = schemars::schema_for!(Scene);
    serde_json::to_string_pretty(&schema).expect("schema serialises") + "\n"
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tiny_scene() -> Scene {
        Scene {
            rooms: vec![Room {
                id: "r1".into(),
                name: "Shop".into(),
                kind: RoomKind::Shop,
                storey: 0,
                floor: Polygon2::rectangle(Vec2::new(0.0, 0.0), Vec2::new(4.0, 3.0)),
                ceiling_height: 2.7,
                walls: vec![],
                openings: vec![],
                objects: vec![Object {
                    id: "o1".into(),
                    category: "counter".into(),
                    center: Vec3::new(1.0, 0.5, 1.0),
                    size: Vec3::new(1.2, 1.0, 0.6),
                    yaw: 0.0,
                    top_height: 1.0,
                    confidence: 0.9,
                    source: ObjectSource::Roomplan,
                    attributes: BTreeMap::new(),
                }],
            }],
            observations: vec![Observation {
                id: "ob1".into(),
                subject_id: "o1".into(),
                metric: "braille_present".into(),
                value: ObservationValue::Bool(true),
                unit: None,
                source: ObservationSource::Photo,
                confidence: 0.8,
            }],
            ..Scene::default()
        }
    }

    #[test]
    fn scene_round_trips_through_json() {
        let scene = tiny_scene();
        assert_eq!(Scene::from_json(&scene.to_json()).unwrap(), scene);
    }

    #[test]
    fn upsert_replaces_by_id() {
        let mut scene = tiny_scene();
        let mut room = scene.rooms[0].clone();
        room.name = "Renamed".into();
        assert!(scene.upsert_room(room));
        assert_eq!(scene.rooms.len(), 1);
        assert_eq!(scene.rooms[0].name, "Renamed");
    }

    #[test]
    fn checked_in_schema_matches_model() {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../schema/scene.schema.json");
        let current = scene_json_schema();
        let on_disk = std::fs::read_to_string(path).unwrap_or_default();
        if on_disk != current {
            std::fs::write(path, &current).expect("write schema");
        }
        assert!(current.contains("\"Scene\""));
    }
}
