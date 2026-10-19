//! Scenes for the benchmarks: the Apple RoomPlan samples and a synthetic ten-room floor.

use sp_core::Engine;
use sp_core::geometry::{Polygon2, Vec2, Vec3};
use sp_core::mesh::{MeshClass, MeshPart, ScanMesh};
use sp_core::roomplan::{import_captured_json, merge_rooms};
use sp_core::scene::{Object, ObjectSource, Opening, OpeningKind, Room, RoomKind, Scene, Wall};
use std::path::PathBuf;

pub const APPLE_SAMPLES: [&str; 2] = ["apple_bedroom3.room.json", "apple_livingroom.room.json"];
const ROOM_WIDTH: f64 = 3.5;
const ROOM_DEPTH: f64 = 4.0;
const CORRIDOR_WIDTH: f64 = 1.8;

fn repo_file(relative: &str) -> String {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").join(relative);
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()))
}

pub fn apple_capture(name: &str) -> String {
    repo_file(&format!("packages/fixtures/standardphysics_fixtures/data/real/{name}"))
}

/// The engine over the repo's catalog and both rulepacks.
pub fn repo_engine() -> Engine {
    let (catalog, ada, cbc) =
        (repo_file("rules/metrics.json"), repo_file("rules/ada2010.json"), repo_file("rules/cbc11b.json"));
    Engine::new(&catalog, &[&ada, &cbc]).expect("repo rules load")
}

pub fn apple_scene() -> Scene {
    let rooms =
        APPLE_SAMPLES.iter().flat_map(|name| import_captured_json(&apple_capture(name)).expect("sample imports"));
    merge_rooms(rooms.collect())
}

/// A corridor along +X with `side_rooms` rooms north of it, each with its own door and fixtures;
/// the corridor's west door is the entrance.
pub fn synthetic_scene(side_rooms: usize) -> Scene {
    let length = ROOM_WIDTH * side_rooms as f64;
    let mut corridor = rect_room("corridor", RoomKind::Corridor, Vec2::ZERO, length, CORRIDOR_WIDTH);
    corridor.openings.push(door("entrance", "corridor-w3", Vec3::new(0.0, 1.0, CORRIDOR_WIDTH / 2.0), 0.95));
    let mut rooms = vec![corridor];
    rooms.extend((0..side_rooms).map(side_room));
    merge_rooms(rooms)
}

fn side_room(index: usize) -> Room {
    let id = format!("room{index}");
    let origin = Vec2::new(ROOM_WIDTH * index as f64, CORRIDOR_WIDTH);
    let kind = [RoomKind::Restroom, RoomKind::Office, RoomKind::Shop][index % 3];
    let mut room = rect_room(&id, kind, origin, ROOM_WIDTH, ROOM_DEPTH);
    room.openings.push(door(
        &format!("{id}-door"),
        &format!("{id}-w0"),
        Vec3::new(origin.x + 0.8, 1.0, origin.y),
        0.95,
    ));
    room.objects = furnish(&id, kind, origin);
    room
}

fn furnish(id: &str, kind: RoomKind, origin: Vec2) -> Vec<Object> {
    let at = |dx: f64, dz: f64| Vec2::new(origin.x + dx, origin.y + dz);
    match kind {
        RoomKind::Restroom => vec![
            object(&format!("{id}-toilet"), "toilet", at(3.0, 3.6), Vec3::new(0.4, 0.75, 0.7), 0.0),
            object(&format!("{id}-sink"), "sink", at(1.2, 3.75), Vec3::new(0.55, 0.2, 0.45), 0.65),
            object(&format!("{id}-bar"), "grab_bar", at(2.8, 3.95), Vec3::new(1.07, 0.04, 0.04), 0.86),
        ],
        RoomKind::Office => vec![
            object(&format!("{id}-table"), "table", at(1.8, 2.5), Vec3::new(1.4, 0.74, 0.8), 0.0),
            object(&format!("{id}-chair"), "chair", at(1.8, 1.7), Vec3::new(0.5, 0.9, 0.5), 0.0),
            object(&format!("{id}-storage"), "storage", at(3.2, 3.5), Vec3::new(0.5, 1.8, 0.9), 0.0),
        ],
        _ => vec![
            object(&format!("{id}-counter"), "counter", at(1.8, 3.4), Vec3::new(2.0, 0.92, 0.6), 0.0),
            object(&format!("{id}-shelf"), "storage", at(0.4, 2.0), Vec3::new(0.5, 1.8, 1.6), 0.0),
        ],
    }
}

/// Rectangular room with walls w0 (south) .. w3 (west), counter-clockwise.
fn rect_room(id: &str, kind: RoomKind, origin: Vec2, width: f64, depth: f64) -> Room {
    let c = [origin, origin + Vec2::new(width, 0.0), origin + Vec2::new(width, depth), origin + Vec2::new(0.0, depth)];
    let walls = (0..4).map(|i| Wall {
        id: format!("{id}-w{i}"),
        start: c[i],
        end: c[(i + 1) % 4],
        height: 2.7,
        thickness: 0.1,
    });
    Room {
        id: id.into(),
        name: id.into(),
        kind,
        storey: 0,
        floor: Polygon2::new(c.to_vec()),
        ceiling_height: 2.7,
        walls: walls.collect(),
        openings: vec![],
        objects: vec![],
    }
}

fn door(id: &str, wall_id: &str, center: Vec3, width: f64) -> Opening {
    Opening {
        id: id.into(),
        kind: OpeningKind::Door,
        wall_id: wall_id.into(),
        center,
        width,
        height: 2.03,
        swing: None,
        hardware: None,
    }
}

fn object(id: &str, category: &str, center: Vec2, size: Vec3, bottom: f64) -> Object {
    Object {
        id: id.into(),
        category: category.into(),
        center: Vec3::new(center.x, bottom + size.y / 2.0, center.y),
        size,
        yaw: 0.0,
        top_height: bottom + size.y,
        confidence: 0.9,
        source: ObjectSource::Detector,
        attributes: Default::default(),
    }
}

/// A level floor mesh of 10 cm triangles over the scene's bounds, as ARKit would deliver it.
pub fn flat_floor_mesh(scene: &Scene) -> ScanMesh {
    const STEP: f64 = 0.1;
    let bounds = scene.rooms.iter().map(|r| r.floor.bounds()).reduce(|a, b| a.union(b)).expect("scene has rooms");
    let nx = ((bounds.max.x - bounds.min.x) / STEP).ceil() as u32;
    let nz = ((bounds.max.y - bounds.min.y) / STEP).ceil() as u32;
    let vertex =
        |i: u32, j: u32| Vec3::new(bounds.min.x + f64::from(i) * STEP, 0.0, bounds.min.y + f64::from(j) * STEP);
    let vertices = (0..=nz).flat_map(|j| (0..=nx).map(move |i| vertex(i, j))).collect();
    let at = |i: u32, j: u32| j * (nx + 1) + i;
    let quads = (0..nz).flat_map(|j| (0..nx).map(move |i| (i, j)));
    let faces: Vec<[u32; 3]> = quads
        .flat_map(|(i, j)| [[at(i, j), at(i + 1, j), at(i + 1, j + 1)], [at(i, j), at(i + 1, j + 1), at(i, j + 1)]])
        .collect();
    let classes = Some(vec![MeshClass::Floor; faces.len()]);
    let identity = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0];
    ScanMesh { floor_y: 0.0, parts: vec![MeshPart { id: [0; 16], transform: identity, vertices, faces, classes }] }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;

    #[test]
    fn synthetic_scene_has_ten_rooms_connected_to_the_corridor() {
        let scene = synthetic_scene(9);
        assert_eq!(scene.rooms.len(), 10);
        assert_eq!(scene.connections.len(), 9);
    }

    #[test]
    fn synthetic_scene_evaluates_and_reaches_every_room() {
        let mut engine = repo_engine();
        engine.set_scene(synthetic_scene(9));
        let started = Instant::now();
        let report = engine.evaluate_all();
        eprintln!("synthetic 10-room evaluate_all: {:?}", started.elapsed());
        assert!(report.governing_counts.pass > 0);
        let analysis = engine.analysis(0).expect("storey 0 analysed");
        let unreached: Vec<_> = (0..9)
            .map(|i| format!("room{i}"))
            .filter(|id| analysis.route_to(id).is_none_or(|r| r.leg.is_none()))
            .collect();
        assert!(unreached.is_empty(), "no route to {unreached:?}");
    }
}
