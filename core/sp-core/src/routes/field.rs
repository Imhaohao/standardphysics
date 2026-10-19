use crate::geometry::Bounds2;
use crate::grid::{CellIndex, ClearanceField, DoorGap, OccupancyGrid};

/// 32 in: minimum clear opening of a door (404.2.3).
pub const DOOR_MIN_CLEAR_WIDTH: f64 = 0.8128;
/// Field value for cells whose width is judged by a door rule rather than the route rule.
pub const EXEMPT: u16 = u16::MAX;

/// Clearance in millimetres per cell for wheelchair routing: 0 where a wheelchair cannot be,
/// [`EXEMPT`] in the throat of a door wide enough to pass (403.5.1 defers to 404.2.3 there).
#[derive(Debug, Clone)]
pub struct RouteField {
    values: Vec<u16>,
}

impl RouteField {
    /// `door_clear_widths[i]` is the estimated clear width of `grid.doors[i]`.
    pub fn build(grid: &OccupancyGrid, clearance: &ClearanceField, door_clear_widths: &[f64]) -> Self {
        let mut values: Vec<u16> = (0..grid.spec.len()).map(|i| free_clearance_mm(grid, clearance, i)).collect();
        for (door_index, gap) in grid.doors.iter().enumerate() {
            let wide_enough = door_clear_widths.get(door_index).is_some_and(|w| *w >= DOOR_MIN_CLEAR_WIDTH);
            if wide_enough {
                exempt_door_throat(grid, &mut values, gap);
            }
        }
        Self { values }
    }

    pub fn value(&self, index: CellIndex) -> u16 {
        self.values[index]
    }

    pub fn is_exempt(&self, index: CellIndex) -> bool {
        self.values[index] == EXEMPT
    }

    pub fn is_passable(&self, index: CellIndex) -> bool {
        self.values[index] > 0
    }

    pub fn len(&self) -> usize {
        self.values.len()
    }

    pub fn is_empty(&self) -> bool {
        self.values.is_empty()
    }
}

fn free_clearance_mm(grid: &OccupancyGrid, clearance: &ClearanceField, index: CellIndex) -> u16 {
    if !grid.is_free(index) {
        return 0;
    }
    (clearance.at(index) * 1000.0).round().clamp(1.0, f64::from(EXEMPT - 1)) as u16
}

/// The door passage plus a disc of the door's half-width either side, where the jambs, not the
/// route, set the width.
fn exempt_door_throat(grid: &OccupancyGrid, values: &mut [u16], gap: &DoorGap) {
    let radius = gap.width / 2.0;
    let disc_bounds = Bounds2::around(&[gap.center]).expanded(radius);
    let disc = grid.spec.cells_in(disc_bounds).filter(|&i| grid.spec.center(i).distance(gap.center) <= radius);
    let passage = gap.passage(grid.options.door_gap_margin);
    let throat = grid.spec.cells_in(passage.bounds()).filter(|&i| passage.contains(grid.spec.center(i)));
    let cells: Vec<CellIndex> = disc.chain(throat).collect();
    for cell in cells {
        if grid.is_free(cell) {
            values[cell] = EXEMPT;
        }
    }
}

#[cfg(test)]
impl RouteField {
    pub(crate) fn from_values(values: Vec<u16>) -> Self {
        Self { values }
    }
}
