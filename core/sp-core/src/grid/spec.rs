use crate::geometry::{Bounds2, Vec2};

pub type CellIndex = usize;

/// Placement of a regular grid of square cells in plan.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GridSpec {
    pub origin: Vec2,
    pub cell: f64,
    pub nx: usize,
    pub ny: usize,
}

impl GridSpec {
    /// A grid covering `bounds` with cells of `cell` metres, snapped so cell edges sit on multiples of `cell`.
    pub fn covering(bounds: Bounds2, cell: f64) -> Self {
        let min = Vec2::new((bounds.min.x / cell).floor() * cell, (bounds.min.y / cell).floor() * cell);
        let nx = ((bounds.max.x - min.x) / cell).ceil().max(1.0) as usize;
        let ny = ((bounds.max.y - min.y) / cell).ceil().max(1.0) as usize;
        Self { origin: min, cell, nx, ny }
    }

    pub fn len(&self) -> usize {
        self.nx * self.ny
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub fn index(&self, ix: usize, iy: usize) -> CellIndex {
        iy * self.nx + ix
    }

    pub fn coords(&self, index: CellIndex) -> (usize, usize) {
        (index % self.nx, index / self.nx)
    }

    pub fn center(&self, index: CellIndex) -> Vec2 {
        let (ix, iy) = self.coords(index);
        self.center_of(ix, iy)
    }

    pub fn center_of(&self, ix: usize, iy: usize) -> Vec2 {
        Vec2::new(self.origin.x + (ix as f64 + 0.5) * self.cell, self.origin.y + (iy as f64 + 0.5) * self.cell)
    }

    /// The cell containing `point`, if it lies on the grid.
    pub fn locate(&self, point: Vec2) -> Option<CellIndex> {
        let fx = (point.x - self.origin.x) / self.cell;
        let fy = (point.y - self.origin.y) / self.cell;
        let inside = fx >= 0.0 && fy >= 0.0 && (fx as usize) < self.nx && (fy as usize) < self.ny;
        inside.then(|| self.index(fx as usize, fy as usize))
    }

    /// Inclusive cell ranges whose centres may fall inside `bounds`.
    pub fn cell_range(&self, bounds: Bounds2) -> Option<(std::ops::RangeInclusive<usize>, std::ops::RangeInclusive<usize>)> {
        let to_cell = |v: f64, origin: f64, n: usize| ((v - origin) / self.cell - 0.5).clamp(0.0, (n - 1) as f64);
        if bounds.is_empty() || self.is_empty() {
            return None;
        }
        let x0 = to_cell(bounds.min.x, self.origin.x, self.nx).ceil() as usize;
        let x1 = to_cell(bounds.max.x, self.origin.x, self.nx).floor() as usize;
        let y0 = to_cell(bounds.min.y, self.origin.y, self.ny).ceil() as usize;
        let y1 = to_cell(bounds.max.y, self.origin.y, self.ny).floor() as usize;
        (x0 <= x1 && y0 <= y1).then_some((x0..=x1, y0..=y1))
    }

    /// Columns whose cell centres lie within `[x0, x1]`.
    pub fn column_span(&self, x0: f64, x1: f64) -> Option<std::ops::RangeInclusive<usize>> {
        let first = ((x0 - self.origin.x) / self.cell - 0.5).ceil().max(0.0);
        let last = ((x1 - self.origin.x) / self.cell - 0.5).floor().min(self.nx as f64 - 1.0);
        (first <= last).then(|| first as usize..=last as usize)
    }

    /// Cells whose centres lie inside `bounds`.
    pub fn cells_in(&self, bounds: Bounds2) -> impl Iterator<Item = CellIndex> + '_ {
        let ranges = self.cell_range(bounds);
        ranges.into_iter().flat_map(move |(xs, ys)| ys.flat_map(move |iy| xs.clone().map(move |ix| self.index(ix, iy))))
    }

    /// The 8-connected neighbours of a cell with the step length in cells.
    pub fn neighbours(&self, index: CellIndex) -> impl Iterator<Item = (CellIndex, f64)> + '_ {
        const STEPS: [(isize, isize, f64); 8] = [
            (1, 0, 1.0),
            (-1, 0, 1.0),
            (0, 1, 1.0),
            (0, -1, 1.0),
            (1, 1, std::f64::consts::SQRT_2),
            (1, -1, std::f64::consts::SQRT_2),
            (-1, 1, std::f64::consts::SQRT_2),
            (-1, -1, std::f64::consts::SQRT_2),
        ];
        let (ix, iy) = self.coords(index);
        STEPS.iter().filter_map(move |&(dx, dy, len)| {
            let nx = ix.checked_add_signed(dx).filter(|x| *x < self.nx)?;
            let ny = iy.checked_add_signed(dy).filter(|y| *y < self.ny)?;
            Some((self.index(nx, ny), len))
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn locate_and_center_round_trip() {
        let spec = GridSpec::covering(Bounds2 { min: Vec2::new(-1.0, -1.0), max: Vec2::new(1.0, 1.0) }, 0.025);
        assert_eq!(spec.nx, 80);
        let index = spec.locate(Vec2::new(0.3, -0.2)).unwrap();
        assert!(spec.center(index).distance(Vec2::new(0.3, -0.2)) < 0.025);
    }

    #[test]
    fn cells_in_bounds_are_those_whose_centres_lie_inside() {
        let spec = GridSpec { origin: Vec2::ZERO, cell: 1.0, nx: 10, ny: 10 };
        let cells: Vec<_> = spec.cells_in(Bounds2 { min: Vec2::new(1.2, 1.0), max: Vec2::new(3.5, 2.0) }).collect();
        assert_eq!(cells.len(), 3);
        assert_eq!(spec.neighbours(0).count(), 3);
    }
}
