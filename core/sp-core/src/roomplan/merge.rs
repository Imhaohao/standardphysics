use crate::geometry::Vec2;
use crate::scene::{Opening, Room, RoomConnection, Scene};

/// Doors captured from both sides land within this distance of each other.
const SHARED_OPENING_TOLERANCE: f64 = 0.35;
/// How far past an opening to look for the neighbouring room's floor.
const PROBE_DISTANCE: f64 = 0.3;

/// Merge separately captured rooms into one Scene, detecting which openings connect rooms on the
/// same storey. Rooms keep their own ids; a later room with a duplicate id replaces the earlier one.
pub fn merge_rooms(rooms: Vec<Room>) -> Scene {
    let mut scene = Scene::default();
    for room in rooms {
        scene.upsert_room(room);
    }
    scene.connections = detect_connections(&scene.rooms);
    scene
}

pub fn detect_connections(rooms: &[Room]) -> Vec<RoomConnection> {
    let mut connections: Vec<RoomConnection> = Vec::new();
    for (i, room) in rooms.iter().enumerate() {
        for other in rooms.iter().skip(i + 1).filter(|o| o.storey == room.storey) {
            connections.extend(connections_between(room, other));
        }
    }
    connections
}

fn connections_between(a: &Room, b: &Room) -> Vec<RoomConnection> {
    let from_a = passable(a).filter(|o| opens_into(o, a, b)).map(|o| connection(a, b, &o.id));
    let from_b = passable(b).filter(|o| opens_into(o, b, a) && !mirrors_any(o, a)).map(|o| connection(b, a, &o.id));
    from_a.chain(from_b).collect()
}

fn passable(room: &Room) -> impl Iterator<Item = &Opening> {
    room.openings.iter().filter(|o| o.kind.is_passable())
}

fn connection(from: &Room, to: &Room, opening_id: &str) -> RoomConnection {
    RoomConnection { from_room: from.id.clone(), to_room: to.id.clone(), opening_id: Some(opening_id.to_string()) }
}

fn mirrors_any(opening: &Opening, room: &Room) -> bool {
    passable(room).any(|o| o.center.plan().distance(opening.center.plan()) < SHARED_OPENING_TOLERANCE)
}

/// True when `opening` in `host` is matched by an opening in `neighbour`, or leads onto its floor.
fn opens_into(opening: &Opening, host: &Room, neighbour: &Room) -> bool {
    mirrors_any(opening, neighbour) || probes_reach(opening, host, neighbour)
}

fn probes_reach(opening: &Opening, host: &Room, neighbour: &Room) -> bool {
    let Some(wall) = host.walls.iter().find(|w| w.id == opening.wall_id) else {
        return false;
    };
    let normal = wall.segment().direction().perpendicular();
    let center = opening.center.plan();
    let probe = |dir: Vec2| center + dir * PROBE_DISTANCE;
    [probe(normal), probe(-normal)].into_iter().any(|p| neighbour.floor.contains(p) && !host.floor.contains(p))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::{Polygon2, Vec3};
    use crate::scene::{OpeningKind, RoomKind, Wall};

    fn room(id: &str, min_x: f64, door_x: Option<f64>) -> Room {
        let max_x = min_x + 3.0;
        let wall = Wall { id: format!("{id}-east"), start: Vec2::new(3.0, 0.0), end: Vec2::new(3.0, 3.0), height: 2.5, thickness: 0.1 };
        let openings = door_x
            .map(|x| Opening {
                id: format!("{id}-door"),
                kind: OpeningKind::Door,
                wall_id: wall.id.clone(),
                center: Vec3::new(x, 1.0, 1.5),
                width: 0.9,
                height: 2.0,
                swing: None,
                hardware: None,
            })
            .into_iter()
            .collect();
        Room {
            id: id.into(),
            name: id.into(),
            kind: RoomKind::Other,
            storey: 0,
            floor: Polygon2::rectangle(Vec2::new(min_x, 0.0), Vec2::new(max_x, 3.0)),
            ceiling_height: 2.5,
            walls: vec![wall],
            openings,
            objects: vec![],
        }
    }

    #[test]
    fn door_leading_onto_neighbour_floor_connects_rooms() {
        let scene = merge_rooms(vec![room("a", 0.0, Some(3.0)), room("b", 3.0, None)]);
        assert_eq!(scene.connections.len(), 1);
        assert_eq!(scene.connections[0].opening_id.as_deref(), Some("a-door"));
        assert!(scene.is_interior_opening("a-door"));
    }

    #[test]
    fn same_door_seen_from_both_rooms_is_one_connection() {
        let scene = merge_rooms(vec![room("a", 0.0, Some(3.0)), room("b", 3.0, Some(3.05))]);
        assert_eq!(scene.connections.len(), 1);
    }

    #[test]
    fn rooms_on_other_storeys_never_connect() {
        let mut upstairs = room("b", 3.0, None);
        upstairs.storey = 1;
        assert!(merge_rooms(vec![room("a", 0.0, Some(3.0)), upstairs]).connections.is_empty());
    }
}
