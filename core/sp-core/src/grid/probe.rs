//! Sweeping rectangles across an occupancy grid to measure free floor in a given frame.

use super::{CellState, ClearanceField, OccupancyGrid};
use crate::geometry::{OrientedBox2, Vec2};

/// How far free floor extends, and whether the sweep ran into unscanned space before an obstacle.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Extent {
    pub length: f64,
    pub reached_unscanned: bool,
    pub capped: bool,
}

impl Extent {
    /// Upper bound: unknown when the sweep stopped at unscanned space.
    pub fn upper_bound(&self) -> f64 {
        if self.reached_unscanned { f64::INFINITY } else { self.length }
    }
}

/// A sweep origin: a line segment centred at `origin`, spanning `half_width` along `lateral`, that
/// advances along `forward`.
#[derive(Debug, Clone, Copy)]
pub struct Probe {
    pub origin: Vec2,
    pub forward: Vec2,
    pub lateral: Vec2,
    pub half_width: f64,
}

impl Probe {
    pub fn new(origin: Vec2, forward: Vec2, half_width: f64) -> Self {
        let forward = forward.normalized();
        Self { origin, forward, lateral: forward.perpendicular(), half_width }
    }

    /// Advance until a sample on the sweep line is not free, up to `max_length` metres.
    pub fn sweep(&self, grid: &OccupancyGrid, max_length: f64) -> Extent {
        let step = grid.spec.cell / 2.0;
        let mut travelled = 0.0;
        while travelled + step <= max_length {
            let line_state = self.line_state(grid, travelled + step);
            if line_state != CellState::Free {
                return Extent {
                    length: travelled,
                    reached_unscanned: line_state == CellState::Outside,
                    capped: false,
                };
            }
            travelled += step;
        }
        Extent { length: travelled, reached_unscanned: false, capped: true }
    }

    /// Like [`Probe::sweep`], but first steps over up to `skip` metres of non-free floor at the
    /// origin (the wall an element is mounted on), measuring from where free floor starts.
    pub fn sweep_past(&self, grid: &OccupancyGrid, skip: f64, max_length: f64) -> Extent {
        let step = grid.spec.cell / 2.0;
        let mut start = 0.0;
        while start < skip && self.line_state(grid, start) != CellState::Free {
            start += step;
        }
        let shifted = Probe { origin: self.origin + self.forward * start, ..*self };
        shifted.sweep(grid, max_length)
    }

    /// True when the whole sweep line at `distance` is free floor.
    pub fn is_clear_at(&self, grid: &OccupancyGrid, distance: f64) -> bool {
        self.line_state(grid, distance) == CellState::Free
    }

    /// Worst state along the sweep line at `distance`: Blocked beats Outside beats Free.
    fn line_state(&self, grid: &OccupancyGrid, distance: f64) -> CellState {
        let step = grid.spec.cell / 2.0;
        let samples = (self.half_width / step).ceil().max(0.0) as i64;
        let centre = self.origin + self.forward * distance;
        let mut worst = CellState::Free;
        for k in -samples..=samples {
            let offset = (k as f64 * step).clamp(-self.half_width, self.half_width);
            match grid.state_at(centre + self.lateral * offset) {
                CellState::Free => {}
                CellState::Outside => worst = CellState::Outside,
                _ => return CellState::Blocked,
            }
        }
        worst
    }
}

/// True when every cell centre inside `area` is free floor.
pub fn area_is_free(grid: &OccupancyGrid, area: &OrientedBox2) -> bool {
    grid.spec.cells_in(area.bounds()).filter(|&i| area.contains(grid.spec.center(i))).all(|i| grid.is_free(i))
}

/// Spacing of the coarse samples [`area_is_clear`] tries before scanning every cell.
const CLEAR_SAMPLE: f64 = 0.1;

/// Same answer as [`area_is_free`], faster: a coarse lattice of samples either finds a blocked cell
/// inside the area or, when every sample's clearance covers its share of the area, proves it free;
/// only areas that graze an obstacle fall back to the cell-by-cell scan.
pub fn area_is_clear(grid: &OccupancyGrid, clearance: &ClearanceField, area: &OrientedBox2) -> bool {
    let cover = (CLEAR_SAMPLE + grid.spec.cell) * std::f64::consts::FRAC_1_SQRT_2;
    let mut proven = true;
    for point in area_lattice(area, CLEAR_SAMPLE) {
        let Some(cell) = grid.spec.locate(point) else { return false };
        if !grid.is_free(cell) && area.contains(grid.spec.center(cell)) {
            return false;
        }
        proven &= clearance.at(cell) >= cover;
    }
    proven || area_is_free(grid, area)
}

/// Points spread evenly over the box, no further than `spacing` apart along either side.
fn area_lattice(area: &OrientedBox2, spacing: f64) -> impl Iterator<Item = Vec2> + '_ {
    let size = area.half_extents * 2.0;
    let (nx, nz) = ((size.x / spacing).ceil().max(1.0) as usize, (size.y / spacing).ceil().max(1.0) as usize);
    let (x_axis, z_axis) = area.axes();
    (0..nz).flat_map(move |j| {
        (0..nx).map(move |i| {
            let local_x = size.x * ((i as f64 + 0.5) / nx as f64 - 0.5);
            let local_z = size.y * ((j as f64 + 0.5) / nz as f64 - 0.5);
            area.center + x_axis * local_x + z_axis * local_z
        })
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::grid::GridOptions;
    use crate::grid::occupancy::tests::box_room;

    #[test]
    fn sweep_from_wall_reaches_the_table() {
        let room = box_room();
        let grid = OccupancyGrid::build(&[&room], GridOptions::default());
        let probe = Probe::new(Vec2::new(0.6, 0.06), Vec2::new(0.0, 1.0), 0.2);
        let extent = probe.sweep(&grid, 5.0);
        assert!((extent.length - 2.88).abs() < 0.05, "{extent:?}");
        assert!(!extent.reached_unscanned);
    }

    #[test]
    fn sweep_through_door_reports_unscanned_space() {
        let room = box_room();
        let grid = OccupancyGrid::build(&[&room], GridOptions::default());
        let extent = Probe::new(Vec2::new(2.0, 0.5), Vec2::new(0.0, -1.0), 0.3).sweep(&grid, 5.0);
        assert!(extent.reached_unscanned);
        assert_eq!(extent.upper_bound(), f64::INFINITY);
    }

    proptest::proptest! {
        #[test]
        fn area_is_clear_agrees_with_the_cell_scan(x in 0.0..4.0f64, z in 0.0..3.0f64, w in 0.1..2.0f64, d in 0.1..2.0f64, yaw in 0.0..6.3f64) {
            let room = box_room();
            let grid = OccupancyGrid::build(&[&room], GridOptions::default());
            let clearance = ClearanceField::compute(grid.spec, |i| !grid.is_free(i));
            let area = OrientedBox2::new(Vec2::new(x, z), w, d, yaw);
            proptest::prop_assert_eq!(area_is_clear(&grid, &clearance, &area), area_is_free(&grid, &area));
        }
    }
}
