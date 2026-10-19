use super::categories::{object_category, room_kind, snake_case};
use super::raw::{CapturedObject, CapturedRoom, CapturedStructure, Section, Surface, confidence_value, enum_case};
use crate::geometry::{Polygon2, Vec2, Vec3};
use crate::scene::{Object, ObjectSource, Opening, OpeningKind, Room, Wall, default_wall_thickness};
use serde_json::Value;
use std::collections::BTreeMap;

const DEFAULT_CEILING_HEIGHT: f64 = 2.4;

#[derive(Debug, thiserror::Error)]
pub enum ImportError {
    #[error("RoomPlan JSON did not parse: {0}")]
    Json(#[from] serde_json::Error),
    #[error("RoomPlan capture has no walls and no floor, so the room outline is unknown")]
    NoOutline,
}

/// Import a `CapturedRoom` or a `CapturedStructure` (which holds `rooms`). Returns one Room per
/// captured room, each with its floor at y = 0.
pub fn import_captured_json(json: &str) -> Result<Vec<Room>, ImportError> {
    let value: Value = serde_json::from_str(json)?;
    let has_rooms = value.get("rooms").and_then(Value::as_array).is_some_and(|rooms| !rooms.is_empty());
    let rooms = if has_rooms {
        serde_json::from_value::<CapturedStructure>(value)?.rooms
    } else {
        vec![serde_json::from_value::<CapturedRoom>(value)?]
    };
    rooms.iter().enumerate().map(|(index, room)| import_room(room, index)).collect()
}

pub fn import_room(raw: &CapturedRoom, index: usize) -> Result<Room, ImportError> {
    let floor_level = floor_level(raw);
    let floor = floor_outline(raw).ok_or(ImportError::NoOutline)?;
    let walls: Vec<Wall> = raw.walls.iter().map(|w| convert_wall(w, floor_level)).collect();
    let section = room_section(raw, &floor);
    let openings = convert_openings(raw, &walls, floor_level);
    Ok(Room {
        id: room_id(raw, index),
        name: section.map(|s| humanize(&s.label)).unwrap_or_else(|| format!("Room {}", index + 1)),
        kind: section.map(|s| room_kind(&s.label)).unwrap_or_default(),
        storey: raw.story,
        ceiling_height: walls.iter().map(|w| w.height).fold(0.0, f64::max).max(0.0).max(min_ceiling(&walls)),
        floor,
        walls,
        openings,
        objects: raw.objects.iter().map(|o| convert_object(o, floor_level)).collect(),
    })
}

fn min_ceiling(walls: &[Wall]) -> f64 {
    if walls.is_empty() { DEFAULT_CEILING_HEIGHT } else { 0.0 }
}

fn room_id(raw: &CapturedRoom, index: usize) -> String {
    raw.identifier
        .clone()
        .or_else(|| raw.floors.first().map(|f| f.identifier.clone()))
        .or_else(|| raw.walls.first().map(|w| format!("room-{}", w.identifier)))
        .unwrap_or_else(|| format!("room-{index}"))
}

/// World Y of the floor: the floor surface if captured, else the lowest wall or object bottom.
fn floor_level(raw: &CapturedRoom) -> f64 {
    let floors = raw.floors.iter().map(|f| f.transform.translation().y);
    let walls = raw.walls.iter().map(|w| w.transform.translation().y - w.dimensions[1] / 2.0);
    let objects = raw.objects.iter().map(|o| o.transform.translation().y - o.dimensions[1] / 2.0);
    let lowest = |it: &mut dyn Iterator<Item = f64>| it.fold(f64::INFINITY, f64::min);
    [lowest(&mut floors.into_iter()), lowest(&mut walls.into_iter()), lowest(&mut objects.into_iter())]
        .into_iter()
        .find(|y| y.is_finite())
        .unwrap_or(0.0)
}

fn floor_outline(raw: &CapturedRoom) -> Option<Polygon2> {
    let largest = raw.floors.iter().map(floor_polygon).filter(Polygon2::is_valid).max_by(|a, b| a.area().total_cmp(&b.area()));
    largest.or_else(|| outline_from_walls(&raw.walls))
}

fn floor_polygon(floor: &Surface) -> Polygon2 {
    let corners: Vec<Vec3> = if floor.polygon_corners.len() >= 3 {
        floor.polygon_corners.iter().map(|c| Vec3::new(c[0], c[1], c[2])).collect()
    } else {
        let (hw, hh) = (floor.dimensions[0] / 2.0, floor.dimensions[1] / 2.0);
        vec![Vec3::new(-hw, -hh, 0.0), Vec3::new(hw, -hh, 0.0), Vec3::new(hw, hh, 0.0), Vec3::new(-hw, hh, 0.0)]
    };
    Polygon2::new(corners.into_iter().map(|c| floor.transform.apply(c).plan()).collect())
}

/// Wall endpoints ordered by angle about their mean: right for convex rooms, an approximation otherwise.
fn outline_from_walls(walls: &[Surface]) -> Option<Polygon2> {
    let mut points: Vec<Vec2> = walls.iter().flat_map(wall_endpoints).collect();
    if points.len() < 3 {
        return None;
    }
    let n = points.len() as f64;
    let mean = points.iter().fold(Vec2::ZERO, |acc, p| acc + *p) * (1.0 / n);
    points.sort_by(|a, b| angle_about(*a, mean).total_cmp(&angle_about(*b, mean)));
    points.dedup_by(|a, b| a.distance(*b) < 0.05);
    Some(Polygon2::new(points)).filter(Polygon2::is_valid)
}

fn angle_about(p: Vec2, origin: Vec2) -> f64 {
    (p.y - origin.y).atan2(p.x - origin.x)
}

fn wall_endpoints(wall: &Surface) -> [Vec2; 2] {
    let center = wall.transform.translation().plan();
    let half = wall.transform.plan_x_axis() * (wall.dimensions[0] / 2.0);
    [center - half, center + half]
}

fn convert_wall(wall: &Surface, floor_level: f64) -> Wall {
    let [start, end] = wall_endpoints(wall);
    let top = wall.transform.translation().y + wall.dimensions[1] / 2.0 - floor_level;
    Wall {
        id: wall.identifier.clone(),
        start,
        end,
        height: top.max(wall.dimensions[1]),
        thickness: if wall.dimensions[2] > 0.0 { wall.dimensions[2] } else { default_wall_thickness() },
    }
}

fn convert_openings(raw: &CapturedRoom, walls: &[Wall], floor_level: f64) -> Vec<Opening> {
    let doors = raw.doors.iter().map(|s| (OpeningKind::Door, s));
    let windows = raw.windows.iter().map(|s| (OpeningKind::Window, s));
    let openings = raw.openings.iter().map(|s| (OpeningKind::Opening, s));
    doors.chain(openings).chain(windows).map(|(kind, s)| convert_opening(kind, s, walls, floor_level)).collect()
}

fn convert_opening(kind: OpeningKind, surface: &Surface, walls: &[Wall], floor_level: f64) -> Opening {
    let world = surface.transform.translation();
    let center = Vec3::new(world.x, world.y - floor_level, world.z);
    let is_open = surface.category.get("door").and_then(|d| d.get("isOpen")).and_then(Value::as_bool);
    Opening {
        id: surface.identifier.clone(),
        kind,
        wall_id: host_wall_id(surface, walls, center.plan()),
        center,
        width: surface.dimensions[0],
        height: surface.dimensions[1],
        swing: None,
        hardware: is_open.filter(|open| *open).map(|_| "captured_open".to_string()),
    }
}

fn host_wall_id(surface: &Surface, walls: &[Wall], center: Vec2) -> String {
    let parent = surface.parent_identifier.as_ref().filter(|id| walls.iter().any(|w| &w.id == *id));
    parent.cloned().unwrap_or_else(|| nearest_wall_id(walls, center))
}

fn nearest_wall_id(walls: &[Wall], point: Vec2) -> String {
    walls
        .iter()
        .min_by(|a, b| a.segment().distance_to(point).total_cmp(&b.segment().distance_to(point)))
        .map(|w| w.id.clone())
        .unwrap_or_default()
}

fn convert_object(object: &CapturedObject, floor_level: f64) -> Object {
    let world = object.transform.translation();
    let size = Vec3::new(object.dimensions[0], object.dimensions[1], object.dimensions[2]);
    let center = Vec3::new(world.x, world.y - floor_level, world.z);
    let roomplan_case = enum_case(&object.category);
    let mut attributes: Vec<(String, String)> = object.attributes.iter().map(|(k, v)| (k.clone(), value_text(v))).collect();
    let category = object_category(roomplan_case, &attributes);
    attributes.push(("roomplan_category".into(), roomplan_case.to_string()));
    Object {
        id: object.identifier.clone(),
        category,
        center,
        size,
        yaw: object.transform.yaw(),
        top_height: center.y + size.y / 2.0,
        confidence: confidence_value(&object.confidence),
        source: ObjectSource::Roomplan,
        attributes: attributes.into_iter().collect::<BTreeMap<_, _>>(),
    }
}

fn value_text(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        other => other.to_string(),
    }
}

fn room_section<'a>(raw: &'a CapturedRoom, floor: &Polygon2) -> Option<&'a Section> {
    let inside = raw.sections.iter().find(|s| floor.contains(Vec2::new(s.center[0], s.center[2])));
    inside.or_else(|| raw.sections.first())
}

fn humanize(label: &str) -> String {
    let words = snake_case(label).replace('_', " ");
    let mut chars = words.chars();
    chars.next().map(|first| first.to_uppercase().collect::<String>() + chars.as_str()).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn humanize_section_labels() {
        assert_eq!(humanize("livingRoom"), "Living room");
    }

    #[test]
    fn imports_minimal_room_from_walls_only() {
        let json = r#"{"walls":[
          {"identifier":"w1","dimensions":[4,2.5,0],"transform":[1,0,0,0, 0,1,0,0, 0,0,1,0, 0,1.25,-1.5,1]},
          {"identifier":"w2","dimensions":[4,2.5,0],"transform":[1,0,0,0, 0,1,0,0, 0,0,1,0, 0,1.25,1.5,1]},
          {"identifier":"w3","dimensions":[3,2.5,0],"transform":[0,0,-1,0, 0,1,0,0, 1,0,0,0, 2,1.25,0,1]},
          {"identifier":"w4","dimensions":[3,2.5,0],"transform":[0,0,-1,0, 0,1,0,0, 1,0,0,0, -2,1.25,0,1]}],
          "doors":[{"identifier":"d1","parentIdentifier":"w1","category":{"door":{"isOpen":false}},
            "dimensions":[0.9144,2.03,0],"transform":[1,0,0,0, 0,1,0,0, 0,0,1,0, 0,1.015,-1.5,1]}]}"#;
        let rooms = import_captured_json(json).unwrap();
        let room = &rooms[0];
        assert!((room.floor.area() - 12.0).abs() < 1e-6);
        assert_eq!(room.openings[0].wall_id, "w1");
        assert!((room.openings[0].bottom_height()).abs() < 1e-9);
        assert!((room.ceiling_height - 2.5).abs() < 1e-9);
    }
}
