//! Exact Euclidean distance transform (Felzenszwalb & Huttenlocher 2012): two passes of the 1D
//! lower envelope of parabolas, O(n) in the number of cells.

use super::{CellIndex, GridSpec};

/// Squared distance, in cells, from each cell centre to the nearest cell where `is_obstacle` is
/// true. Cells with no obstacle anywhere on the grid get `f64::INFINITY`.
pub fn squared_distance_transform(nx: usize, ny: usize, is_obstacle: impl Fn(usize) -> bool) -> Vec<f64> {
    let mut grid: Vec<f64> = (0..nx * ny).map(|i| if is_obstacle(i) { 0.0 } else { f64::INFINITY }).collect();
    let mut scratch = Scratch::new(nx.max(ny));
    for row in grid.chunks_mut(nx) {
        scratch.transform_line(row.iter().copied(), row.len());
        row.copy_from_slice(&scratch.output[..nx]);
    }
    for x in 0..nx {
        scratch.transform_line((0..ny).map(|y| grid[y * nx + x]), ny);
        for (y, value) in scratch.output[..ny].iter().enumerate() {
            grid[y * nx + x] = *value;
        }
    }
    grid
}

struct Scratch {
    input: Vec<f64>,
    output: Vec<f64>,
    vertices: Vec<usize>,
    boundaries: Vec<f64>,
}

impl Scratch {
    fn new(n: usize) -> Self {
        Self { input: vec![0.0; n], output: vec![0.0; n], vertices: vec![0; n], boundaries: vec![0.0; n + 1] }
    }

    fn transform_line(&mut self, values: impl Iterator<Item = f64>, n: usize) {
        for (slot, value) in self.input.iter_mut().zip(values) {
            *slot = value;
        }
        let hull = self.lower_envelope(n);
        if hull == 0 {
            self.output[..n].fill(f64::INFINITY);
            return;
        }
        self.sample_envelope(n, hull);
    }

    /// Builds the lower envelope of the parabolas rooted at finite samples; returns its size.
    fn lower_envelope(&mut self, n: usize) -> usize {
        let mut k = 0usize;
        for q in (0..n).filter(|&q| self.input[q].is_finite()) {
            while k > 0 && self.intersection(self.vertices[k - 1], q) <= self.boundaries[k - 1] {
                k -= 1;
            }
            self.vertices[k] = q;
            self.boundaries[k] = if k == 0 { f64::NEG_INFINITY } else { self.intersection(self.vertices[k - 1], q) };
            k += 1;
        }
        self.boundaries[k] = f64::INFINITY;
        k
    }

    fn intersection(&self, p: usize, q: usize) -> f64 {
        let (fp, fq) = (self.input[p], self.input[q]);
        let (p, q) = (p as f64, q as f64);
        ((fq + q * q) - (fp + p * p)) / (2.0 * (q - p))
    }

    fn sample_envelope(&mut self, n: usize, hull: usize) {
        let mut k = 0usize;
        for q in 0..n {
            while k + 1 < hull && self.boundaries[k + 1] < q as f64 {
                k += 1;
            }
            let v = self.vertices[k];
            let d = q as f64 - v as f64;
            self.output[q] = d * d + self.input[v];
        }
    }
}

/// Metres from each free cell to the nearest obstacle edge, so the clear width of a path through a
/// cell's centre is at most `2 * clearance`.
#[derive(Debug, Clone)]
pub struct ClearanceField {
    pub spec: GridSpec,
    values: Vec<f32>,
}

impl ClearanceField {
    pub fn compute(spec: GridSpec, is_obstacle: impl Fn(usize) -> bool) -> Self {
        let squared = squared_distance_transform(spec.nx, spec.ny, is_obstacle);
        let half = spec.cell / 2.0;
        let values = squared.iter().map(|d2| clearance_from_squared(*d2, spec.cell, half)).collect();
        Self { spec, values }
    }

    pub fn at(&self, index: CellIndex) -> f64 {
        f64::from(self.values[index])
    }

    pub fn values(&self) -> &[f32] {
        &self.values
    }

    pub fn clear_width_at(&self, index: CellIndex) -> f64 {
        2.0 * self.at(index)
    }
}

/// Distance from a cell centre to the near edge of the nearest obstacle cell.
fn clearance_from_squared(d2: f64, cell: f64, half: f64) -> f32 {
    if d2 == 0.0 {
        return 0.0;
    }
    if !d2.is_finite() {
        return f32::MAX;
    }
    (d2.sqrt() * cell - half).max(0.0) as f32
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    fn brute_force(nx: usize, ny: usize, obstacles: &[bool]) -> Vec<f64> {
        (0..nx * ny)
            .map(|i| {
                let (x, y) = ((i % nx) as f64, (i / nx) as f64);
                (0..nx * ny)
                    .filter(|&j| obstacles[j])
                    .map(|j| ((j % nx) as f64 - x).powi(2) + ((j / nx) as f64 - y).powi(2))
                    .fold(f64::INFINITY, f64::min)
            })
            .collect()
    }

    #[test]
    fn single_obstacle_gives_squared_euclidean_distance() {
        let d = squared_distance_transform(5, 4, |i| i == 0);
        assert_eq!(d[0], 0.0);
        assert_eq!(d[4], 16.0);
        assert_eq!(d[3 * 5 + 4], 25.0);
    }

    #[test]
    fn empty_grid_is_infinite() {
        assert!(squared_distance_transform(3, 3, |_| false).iter().all(|d| d.is_infinite()));
    }

    #[test]
    fn corridor_clearance_gives_its_width() {
        let spec = GridSpec { origin: crate::geometry::Vec2::ZERO, cell: 0.1, nx: 9, ny: 3 };
        let field = ClearanceField::compute(spec, |i| {
            let x = i % 9;
            x == 0 || x == 8
        });
        assert!((field.clear_width_at(spec.index(4, 1)) - 0.7).abs() < 1e-6);
    }

    proptest! {
        #[test]
        fn matches_brute_force(nx in 1usize..14, ny in 1usize..14, seed in proptest::collection::vec(any::<bool>(), 196)) {
            let obstacles: Vec<bool> = (0..nx * ny).map(|i| seed[i] && seed[(i * 7 + 3) % 196]).collect();
            let fast = squared_distance_transform(nx, ny, |i| obstacles[i]);
            let slow = brute_force(nx, ny, &obstacles);
            for (a, b) in fast.iter().zip(&slow) {
                prop_assert!((a.is_infinite() && b.is_infinite()) || (a - b).abs() < 1e-9);
            }
        }

        #[test]
        fn distance_is_one_lipschitz(nx in 2usize..20, ny in 2usize..20, seed in proptest::collection::vec(any::<bool>(), 400)) {
            let d = squared_distance_transform(nx, ny, |i| seed[i] && seed[(i * 13 + 5) % 400]);
            for y in 0..ny {
                for x in 0..nx - 1 {
                    let (a, b) = (d[y * nx + x].sqrt(), d[y * nx + x + 1].sqrt());
                    prop_assert!((a.is_infinite() && b.is_infinite()) || (a - b).abs() <= 1.0 + 1e-9);
                }
            }
        }

        #[test]
        fn obstacles_are_exactly_the_zeros(nx in 1usize..16, ny in 1usize..16, seed in proptest::collection::vec(any::<bool>(), 256)) {
            let d = squared_distance_transform(nx, ny, |i| seed[i]);
            for (i, value) in d.iter().enumerate() {
                prop_assert_eq!(*value == 0.0, seed[i]);
            }
        }
    }
}
