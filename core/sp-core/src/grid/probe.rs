//! Sweeping rectangles across an occupancy grid to measure free floor in a given frame.

use super::{CellState, OccupancyGrid};
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
                return Extent { length: travelled, reached_unscanned: line_state == CellState::Outside, capped: false };
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
}
