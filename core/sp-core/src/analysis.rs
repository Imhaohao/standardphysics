//! Per-storey spatial analysis shared by every metric: occupancy grid, clearance field, widest-path
//! trees from each entrance, and one route leg per destination.

use crate::geometry::{OrientedBox2, Vec2};
use crate::grid::{CellIndex, ClearanceField, GridOptions, OccupancyGrid};
use crate::mesh::{FloorSurface, ScanMesh};
use crate::routes::{RouteField, RouteLeg, ShortestTree, WidestTree, largest_turning_circle, t_turn_fits, trace_leg};
use crate::scene::{Opening, OpeningKind, Room, Scene};
use crate::units::inches;
use std::collections::{BTreeSet, HashMap};
use std::sync::OnceLock;

/// Door leaf thickness plus stop: subtracted from a door's frame opening to estimate its clear width at 90 degrees.
pub const DOOR_CLEAR_WIDTH_ALLOWANCE: f64 = 0.0508;
/// Free floor this close to an element counts as reaching it.
pub const APPROACH_BAND: f64 = 0.5;

#[derive(Debug, Clone, PartialEq)]
pub struct AnalysisOptions {
    pub grid: GridOptions,
    pub door_clear_width_allowance: f64,
    /// Object categories an accessible route must reach.
    pub destination_categories: BTreeSet<String>,
}

impl Default for AnalysisOptions {
    fn default() -> Self {
        Self {
            grid: GridOptions::default(),
            door_clear_width_allowance: DOOR_CLEAR_WIDTH_ALLOWANCE,
            destination_categories: BTreeSet::new(),
        }
    }
}

/// Estimated clear width of a door or doorway at 90 degrees, metres.
pub fn estimated_clear_width(opening: &Opening, allowance: f64) -> f64 {
    match opening.kind {
        OpeningKind::Door => (opening.width - allowance).max(0.0),
        _ => opening.width,
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum Destination {
    Opening(String),
    Room(String),
    Object(String),
}

impl Destination {
    pub fn id(&self) -> &str {
        match self {
            Destination::Opening(id) | Destination::Room(id) | Destination::Object(id) => id,
        }
    }
}

#[derive(Debug, Clone)]
pub struct RouteRecord {
    pub id: String,
    pub destination: Destination,
    /// Entrance the best leg starts from.
    pub entrance: Option<String>,
    pub leg: Option<RouteLeg>,
    target_cells: Vec<CellIndex>,
}

impl RouteRecord {
    pub fn route_id(destination_id: &str) -> String {
        format!("route:{destination_id}")
    }
}

pub struct StoreyAnalysis {
    pub storey: i32,
    pub grid: OccupancyGrid,
    /// Floor heights and low furniture from the scan mesh, when one was captured for this storey.
    pub surface: Option<FloorSurface>,
    pub clearance: ClearanceField,
    pub field: RouteField,
    pub entrances: Vec<String>,
    trees: Vec<WidestTree>,
    pub routes: Vec<RouteRecord>,
    route_index: HashMap<String, usize>,
    turning_diameters: Vec<f64>,
    room_axes: Vec<f64>,
    t_turns: Vec<OnceLock<bool>>,
    corridor: OnceLock<Vec<bool>>,
    walking: OnceLock<Vec<ShortestTree>>,
}

impl StoreyAnalysis {
    pub fn build(scene: &Scene, storey: i32, options: &AnalysisOptions) -> Self {
        Self::build_with_meshes(scene, storey, options, &[])
    }

    pub fn build_with_meshes(scene: &Scene, storey: i32, options: &AnalysisOptions, meshes: &[&ScanMesh]) -> Self {
        let rooms: Vec<&Room> = scene.rooms_on(storey).collect();
        let mut grid = OccupancyGrid::build(&rooms, options.grid);
        let surface = (!meshes.is_empty()).then(|| FloorSurface::build(grid.spec, meshes));
        if let Some(surface) = &surface {
            grid.block_free_cells(surface.furniture_cells());
        }
        let clearance = ClearanceField::compute(grid.spec, |i| !grid.is_free(i));
        let door_widths = door_clear_widths(&rooms, &grid, options.door_clear_width_allowance);
        let field = RouteField::build(&grid, &clearance, &door_widths);
        let entrances = entrance_ids(scene, &rooms);
        let trees = entrances.iter().map(|id| WidestTree::grow(&grid.spec, &field, &door_cells(&grid, id))).collect();
        let mut analysis = Self {
            storey,
            turning_diameters: (0..rooms.len()).map(|i| largest_turning_circle(&grid, &clearance, i as u16)).collect(),
            room_axes: rooms.iter().map(|r| dominant_axis(r)).collect(),
            grid,
            surface,
            clearance,
            field,
            entrances,
            trees,
            routes: Vec::new(),
            route_index: HashMap::new(),
            t_turns: rooms.iter().map(|_| OnceLock::new()).collect(),
            corridor: OnceLock::new(),
            walking: OnceLock::new(),
        };
        analysis.trace_routes(&rooms, options);
        analysis
    }

    fn trace_routes(&mut self, rooms: &[&Room], options: &AnalysisOptions) {
        for destination in destinations(rooms, &self.entrances, options) {
            let cells = self.target_cells(rooms, &destination);
            let record = self.best_route(destination, cells);
            self.route_index.insert(record.id.clone(), self.routes.len());
            self.routes.push(record);
        }
    }

    fn target_cells(&self, rooms: &[&Room], destination: &Destination) -> Vec<CellIndex> {
        match destination {
            Destination::Opening(id) => door_cells(&self.grid, id),
            Destination::Room(id) => room_cells(&self.grid, id),
            Destination::Object(id) => {
                let object = rooms.iter().flat_map(|r| &r.objects).find(|o| &o.id == id);
                object.map(|o| approach_cells(&self.grid, &o.footprint())).unwrap_or_default()
            }
        }
    }

    fn best_route(&self, destination: Destination, target_cells: Vec<CellIndex>) -> RouteRecord {
        let best = self
            .trees
            .iter()
            .enumerate()
            .flat_map(|(t, tree)| target_cells.iter().map(move |&c| (tree.bottleneck(c), t, c)))
            .filter(|(width, _, _)| *width > 0)
            .max_by_key(|(width, t, c)| (*width, std::cmp::Reverse(*t), std::cmp::Reverse(*c)));
        let leg = best.and_then(|(_, t, c)| trace_leg(&self.trees[t], &self.field, &self.clearance, c));
        RouteRecord {
            id: RouteRecord::route_id(destination.id()),
            entrance: best.map(|(_, t, _)| self.entrances[t].clone()),
            destination,
            leg,
            target_cells,
        }
    }

    pub fn route(&self, route_id: &str) -> Option<&RouteRecord> {
        self.route_index.get(route_id).map(|&i| &self.routes[i])
    }

    pub fn route_to(&self, destination_id: &str) -> Option<&RouteRecord> {
        self.route(&RouteRecord::route_id(destination_id))
    }

    pub fn turning_diameter(&self, room_id: &str) -> Option<f64> {
        self.grid.room_index(room_id).map(|i| self.turning_diameters[i as usize])
    }

    pub fn t_turn_fits(&self, room_id: &str) -> Option<bool> {
        let index = self.grid.room_index(room_id)? as usize;
        Some(
            *self.t_turns[index]
                .get_or_init(|| t_turn_fits(&self.grid, &self.clearance, index as u16, self.room_axes[index])),
        )
    }

    /// Cells within 18 in of the centreline of a 36 in route reachable from an entrance.
    pub fn route_corridor(&self) -> &[bool] {
        self.corridor.get_or_init(|| self.compute_corridor())
    }

    fn compute_corridor(&self) -> Vec<bool> {
        let half = inches(18.0);
        let threshold = (half * 1000.0).round() as u16;
        let centres = |i: usize| self.trees.iter().any(|t| t.bottleneck(i) >= threshold);
        let to_centre = crate::grid::squared_distance_transform(self.grid.spec.nx, self.grid.spec.ny, centres);
        let reach = (half / self.grid.spec.cell).powi(2) + 1e-9;
        to_centre.iter().enumerate().map(|(i, d2)| *d2 <= reach && self.grid.is_free(i)).collect()
    }

    pub fn is_on_route_corridor(&self, point: Vec2) -> bool {
        self.grid.spec.locate(point).is_some_and(|i| self.route_corridor()[i])
    }

    /// Shortest walking trees (stairs allowed), one per entrance.
    pub fn walking_trees(&self) -> &[ShortestTree] {
        self.walking.get_or_init(|| {
            self.entrances.iter().map(|id| ShortestTree::grow(&self.grid, &door_cells(&self.grid, id))).collect()
        })
    }

    /// Walking distance and path from the nearest entrance to the route's destination.
    pub fn walking_route(&self, record: &RouteRecord) -> Option<(f64, Vec<Vec2>)> {
        let trees = self.walking_trees();
        let best = trees
            .iter()
            .flat_map(|tree| record.target_cells.iter().filter_map(move |&c| tree.distance_to(c).map(|d| (d, tree, c))))
            .min_by(|a, b| a.0.total_cmp(&b.0))?;
        let points = best.1.path_to(best.2).into_iter().map(|c| self.grid.spec.center(c)).collect();
        Some((best.0, points))
    }

    pub fn room_axis(&self, room_id: &str) -> f64 {
        self.grid.room_index(room_id).map(|i| self.room_axes[i as usize]).unwrap_or(0.0)
    }
}

fn door_clear_widths(rooms: &[&Room], grid: &OccupancyGrid, allowance: f64) -> Vec<f64> {
    let openings: HashMap<&str, &Opening> =
        rooms.iter().flat_map(|r| &r.openings).map(|o| (o.id.as_str(), o)).collect();
    grid.doors
        .iter()
        .map(|gap| openings.get(gap.opening_id.as_str()).map(|o| estimated_clear_width(o, allowance)).unwrap_or(0.0))
        .collect()
}

/// Passable openings that do not join two scanned rooms: the ways in from outside the scan.
fn entrance_ids(scene: &Scene, rooms: &[&Room]) -> Vec<String> {
    rooms
        .iter()
        .flat_map(|r| &r.openings)
        .filter(|o| o.kind.is_passable() && !scene.is_interior_opening(&o.id))
        .map(|o| o.id.clone())
        .collect()
}

fn destinations(rooms: &[&Room], entrances: &[String], options: &AnalysisOptions) -> Vec<Destination> {
    let openings = rooms
        .iter()
        .flat_map(|r| &r.openings)
        .filter(|o| o.kind.is_passable() && !entrances.contains(&o.id))
        .map(|o| Destination::Opening(o.id.clone()));
    let room_targets = rooms.iter().map(|r| Destination::Room(r.id.clone()));
    let objects = rooms
        .iter()
        .flat_map(|r| &r.objects)
        .filter(|o| options.destination_categories.contains(&o.category))
        .map(|o| Destination::Object(o.id.clone()));
    openings.chain(room_targets).chain(objects).collect()
}

pub fn door_cells(grid: &OccupancyGrid, opening_id: &str) -> Vec<CellIndex> {
    let Some(index) = grid.door_index(opening_id) else { return Vec::new() };
    let passage = grid.doors[index].passage(grid.options.door_gap_margin);
    grid.spec.cells_in(passage.bounds()).filter(|&i| grid.door[i] == index as u16).collect()
}

fn room_cells(grid: &OccupancyGrid, room_id: &str) -> Vec<CellIndex> {
    let Some(index) = grid.room_index(room_id) else { return Vec::new() };
    (0..grid.spec.len()).filter(|&i| grid.room[i] == index && grid.is_free(i)).collect()
}

/// Free cells within [`APPROACH_BAND`] of an element's footprint.
pub fn approach_cells(grid: &OccupancyGrid, footprint: &OrientedBox2) -> Vec<CellIndex> {
    let band = footprint.grown(APPROACH_BAND);
    grid.spec
        .cells_in(band.bounds())
        .filter(|&i| grid.is_free(i))
        .filter(|&i| {
            let p = grid.spec.center(i);
            band.contains(p) && footprint.distance_to(p) > 0.0
        })
        .collect()
}

/// Direction of the room's longest wall, as a yaw, so turning-space templates align with the room.
pub fn dominant_axis(room: &Room) -> f64 {
    let longest = room.walls.iter().max_by(|a, b| a.length().total_cmp(&b.length()));
    let along = longest
        .map(|w| w.segment().direction())
        .or_else(|| room.floor.edges().max_by(|a, b| a.length().total_cmp(&b.length())).map(|e| e.direction()));
    along.map(|d| (-d.y).atan2(d.x)).unwrap_or(0.0)
}
