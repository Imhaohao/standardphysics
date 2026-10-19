use super::{CellIndex, GridSpec};
use crate::geometry::{Bounds2, OrientedBox2, Polygon2, Segment2, Vec2};
use crate::scene::{Object, Opening, Room, Wall};

/// Objects whose underside is lower than 27 in occupy the floor: a wheelchair cannot pass under
/// them and a cane detects them. Higher objects (wall cabinets, TVs) are protrusions, not obstacles.
pub const BLOCKS_FLOOR_BELOW: f64 = 0.6858;
pub const NONE: u16 = u16::MAX;

/// Categories that describe a zone of floor rather than a solid object.
const ZONE_CATEGORIES: &[&str] = &[
    "fitting_room",
    "toilet_compartment",
    "checkout_aisle",
    "food_service_line",
    "parking_space",
    "access_aisle",
    "passenger_loading_zone",
    "ramp",
    "curb_ramp",
    "detectable_warning",
    "mat",
    "floor_grating",
    "threshold",
    "elevator",
    "platform_lift",
];

pub fn is_zone_category(category: &str) -> bool {
    ZONE_CATEGORIES.contains(&category)
}

pub fn blocks_floor(object: &Object) -> bool {
    object.bottom_height() < BLOCKS_FLOOR_BELOW && !is_zone_category(&object.category)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum CellState {
    /// Not on any scanned floor: unknown space, treated as an obstacle for clearances.
    Outside,
    Free,
    Blocked,
    /// Stairs: walkable, but not by wheelchair.
    Stairs,
}

/// The passage a door or cased opening cuts through its wall.
#[derive(Debug, Clone, PartialEq)]
pub struct DoorGap {
    pub opening_id: String,
    pub room_id: String,
    pub center: Vec2,
    /// Unit vector along the wall.
    pub along: Vec2,
    /// Unit vector across the wall.
    pub normal: Vec2,
    pub width: f64,
    pub wall_thickness: f64,
}

impl DoorGap {
    pub fn passage(&self, margin: f64) -> OrientedBox2 {
        let yaw = (-self.along.y).atan2(self.along.x);
        OrientedBox2::new(self.center, self.width, self.wall_thickness + 2.0 * margin, yaw)
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GridOptions {
    pub cell: f64,
    /// Extra depth carved either side of a wall at a door so adjacent room scans meet.
    pub door_gap_margin: f64,
}

impl Default for GridOptions {
    fn default() -> Self {
        Self { cell: 0.025, door_gap_margin: 0.15 }
    }
}

#[derive(Debug, Clone)]
pub struct OccupancyGrid {
    pub spec: GridSpec,
    pub states: Vec<CellState>,
    /// Index into `room_ids` of the room whose floor holds the cell, or [`NONE`].
    pub room: Vec<u16>,
    /// Index into `doors` of the door passage holding the cell, or [`NONE`].
    pub door: Vec<u16>,
    pub room_ids: Vec<String>,
    pub doors: Vec<DoorGap>,
    pub options: GridOptions,
}

impl OccupancyGrid {
    pub fn build(rooms: &[&Room], options: GridOptions) -> Self {
        let bounds = rooms.iter().map(|r| r.floor.bounds()).fold(Bounds2::EMPTY, Bounds2::union);
        let bounds = if bounds.is_empty() { Bounds2 { min: Vec2::ZERO, max: Vec2::new(1.0, 1.0) } } else { bounds };
        let spec = GridSpec::covering(bounds.expanded(0.5), options.cell);
        let mut grid = Self {
            spec,
            states: vec![CellState::Outside; spec.len()],
            room: vec![NONE; spec.len()],
            door: vec![NONE; spec.len()],
            room_ids: rooms.iter().map(|r| r.id.clone()).collect(),
            doors: Vec::new(),
            options,
        };
        rooms.iter().enumerate().for_each(|(i, room)| grid.fill_floor(&room.floor, i as u16));
        rooms.iter().flat_map(|r| &r.walls).for_each(|w| grid.draw_wall(w));
        rooms.iter().for_each(|room| grid.carve_doors(room));
        rooms.iter().flat_map(|r| &r.objects).for_each(|o| grid.draw_object(o));
        grid
    }

    pub fn state(&self, index: CellIndex) -> CellState {
        self.states[index]
    }

    pub fn is_free(&self, index: CellIndex) -> bool {
        self.states[index] == CellState::Free
    }

    pub fn room_index(&self, room_id: &str) -> Option<u16> {
        self.room_ids.iter().position(|id| id == room_id).map(|i| i as u16)
    }

    pub fn door_index(&self, opening_id: &str) -> Option<usize> {
        self.doors.iter().position(|d| d.opening_id == opening_id)
    }

    pub fn state_at(&self, point: Vec2) -> CellState {
        self.spec.locate(point).map(|i| self.states[i]).unwrap_or(CellState::Outside)
    }

    fn fill_floor(&mut self, floor: &Polygon2, room: u16) {
        if !floor.is_valid() {
            return;
        }
        let Some((_, ys)) = self.spec.cell_range(floor.bounds()) else { return };
        for iy in ys {
            let y = self.spec.center_of(0, iy).y;
            for span in floor.scanline_crossings(y).chunks_exact(2) {
                self.fill_span(iy, span[0], span[1], room);
            }
        }
    }

    fn fill_span(&mut self, iy: usize, x0: f64, x1: f64, room: u16) {
        let Some(xs) = self.spec.column_span(x0, x1) else { return };
        for ix in xs {
            let index = self.spec.index(ix, iy);
            self.states[index] = CellState::Free;
            self.room[index] = room;
        }
    }

    fn draw_wall(&mut self, wall: &Wall) {
        let half = (wall.thickness / 2.0).max(self.spec.cell * 0.75);
        let segment = wall.segment();
        let bounds = Bounds2::around(&[segment.start, segment.end]).expanded(half);
        let cells: Vec<CellIndex> =
            self.spec.cells_in(bounds).filter(|&i| segment.distance_to(self.spec.center(i)) <= half).collect();
        cells.into_iter().for_each(|i| self.states[i] = CellState::Blocked);
    }

    fn carve_doors(&mut self, room: &Room) {
        for opening in room.openings.iter().filter(|o| o.kind.is_passable()) {
            let gap = door_gap(room, opening);
            let passage = gap.passage(self.options.door_gap_margin);
            let index = self.doors.len() as u16;
            let cells: Vec<CellIndex> = self.spec.cells_in(passage.bounds()).filter(|&i| passage.contains(self.spec.center(i))).collect();
            for cell in cells {
                self.states[cell] = CellState::Free;
                self.door[cell] = index;
            }
            self.doors.push(gap);
        }
    }

    fn draw_object(&mut self, object: &Object) {
        if !blocks_floor(object) {
            return;
        }
        let state = if object.category == "stairs" { CellState::Stairs } else { CellState::Blocked };
        let footprint = object.footprint();
        let mut cells: Vec<CellIndex> =
            self.spec.cells_in(footprint.bounds()).filter(|&i| footprint.contains(self.spec.center(i))).collect();
        cells.extend(self.spec.locate(footprint.center));
        cells.into_iter().for_each(|i| self.states[i] = state);
    }
}

/// Where a door passes through its wall. Falls back to the nearest floor edge when the host wall is missing.
pub fn door_gap(room: &Room, opening: &Opening) -> DoorGap {
    let center = opening.center.plan();
    let wall = room.walls.iter().find(|w| w.id == opening.wall_id).map(|w| (w.segment(), w.thickness));
    let (segment, thickness) = wall.unwrap_or_else(|| (nearest_floor_edge(&room.floor, center), crate::scene::default_wall_thickness()));
    let along = segment.direction();
    DoorGap {
        opening_id: opening.id.clone(),
        room_id: room.id.clone(),
        center: segment.closest_point(center),
        along,
        normal: along.perpendicular(),
        width: opening.width,
        wall_thickness: thickness,
    }
}

fn nearest_floor_edge(floor: &Polygon2, point: Vec2) -> Segment2 {
    floor
        .edges()
        .min_by(|a, b| a.distance_to(point).total_cmp(&b.distance_to(point)))
        .unwrap_or(Segment2::new(point, point + Vec2::new(1.0, 0.0)))
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use crate::geometry::Vec3;
    use crate::scene::{ObjectSource, OpeningKind, RoomKind};

    pub(crate) fn box_room() -> Room {
        let corners = [Vec2::new(0.0, 0.0), Vec2::new(4.0, 0.0), Vec2::new(4.0, 3.0), Vec2::new(0.0, 3.0)];
        let walls = (0..4)
            .map(|i| Wall { id: format!("w{i}"), start: corners[i], end: corners[(i + 1) % 4], height: 2.5, thickness: 0.1 })
            .collect();
        Room {
            id: "r".into(),
            name: "r".into(),
            kind: RoomKind::Other,
            storey: 0,
            floor: Polygon2::new(corners.to_vec()),
            ceiling_height: 2.5,
            walls,
            openings: vec![Opening {
                id: "d".into(),
                kind: OpeningKind::Door,
                wall_id: "w0".into(),
                center: Vec3::new(2.0, 1.0, 0.0),
                width: 0.9,
                height: 2.0,
                swing: None,
                hardware: None,
            }],
            objects: vec![Object {
                id: "table".into(),
                category: "table".into(),
                center: Vec3::new(2.0, 0.375, 1.5),
                size: Vec3::new(1.0, 0.75, 1.0),
                yaw: 0.3,
                top_height: 0.75,
                confidence: 1.0,
                source: ObjectSource::Roomplan,
                attributes: Default::default(),
            }],
        }
    }

    #[test]
    fn rasterizes_floor_walls_doors_and_objects() {
        let room = box_room();
        let grid = OccupancyGrid::build(&[&room], GridOptions::default());
        assert_eq!(grid.state_at(Vec2::new(1.0, 1.0)), CellState::Free);
        assert_eq!(grid.state_at(Vec2::new(2.0, 1.5)), CellState::Blocked);
        assert_eq!(grid.state_at(Vec2::new(1.0, 0.0)), CellState::Blocked);
        assert_eq!(grid.state_at(Vec2::new(2.0, 0.0)), CellState::Free);
        assert_eq!(grid.state_at(Vec2::new(2.0, -0.1)), CellState::Free);
        assert_eq!(grid.state_at(Vec2::new(-0.3, 1.0)), CellState::Outside);
        assert_eq!(grid.doors.len(), 1);
    }

    #[test]
    fn high_objects_do_not_block_the_floor() {
        let mut room = box_room();
        room.objects[0].center.y = 1.5;
        let grid = OccupancyGrid::build(&[&room], GridOptions::default());
        assert_eq!(grid.state_at(Vec2::new(2.0, 1.5)), CellState::Free);
    }
}
