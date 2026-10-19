//! A floor height field and a low-furniture layer sampled from the scan mesh, on the storey grid.

use super::format::{MeshClass, MeshPart, ScanMesh};
use crate::geometry::{OrientedBox2, Vec2, Vec3};
use crate::grid::{BLOCKS_FLOOR_BELOW, CellIndex, GridSpec};

/// Faces tilted less than about 25 degrees from level can be floor.
const WALKABLE_NORMAL_Y: f64 = 0.9;
/// Unclassified level surfaces higher than this are furniture tops, not floor; surfaces ARKit
/// classifies as floor may rise further (ramps and raised areas).
const MAX_UNCLASSIFIED_FLOOR_HEIGHT: f64 = 0.3;
const MAX_FLOOR_HEIGHT: f64 = 1.5;
/// Level changes are read between floor samples no further apart than this.
const LEVEL_CHANGE_WINDOW: f64 = 0.1;
/// Furniture geometry rising this far above the local floor (and below 27 in) blocks a wheelchair.
const OBSTACLE_RISE: f64 = 0.2;
/// Typical LiDAR mesh noise, carried as the uncertainty of every mesh-derived value.
pub const HEIGHT_NOISE: f64 = 0.005;
pub const SLOPE_NOISE: f64 = 0.005;
/// A slope estimate needs this share of its area covered by floor samples.
const MIN_COVERAGE: f64 = 0.3;
const MIN_SAMPLES: usize = 12;

/// Least-squares floor plane over an area: height rises by `gradient` per metre in plan.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct FloorPlane {
    pub gradient: Vec2,
    pub samples: usize,
}

impl FloorPlane {
    pub fn slope(&self) -> f64 {
        self.gradient.length()
    }

    pub fn slope_along(&self, direction: Vec2) -> f64 {
        self.gradient.dot(direction.normalized()).abs()
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct LevelChange {
    pub height: f64,
    pub at: Vec2,
}

#[derive(Debug, Clone)]
pub struct FloorSurface {
    spec: GridSpec,
    /// Lowest walkable surface per cell, metres above the storey floor (NaN where unseen).
    floor: Vec<f32>,
    /// Highest table or seat geometry below 27 in per cell (NaN where none).
    furniture: Vec<f32>,
}

impl FloorSurface {
    pub fn build(spec: GridSpec, meshes: &[&ScanMesh]) -> Self {
        let mut surface = Self { spec, floor: vec![f32::NAN; spec.len()], furniture: vec![f32::NAN; spec.len()] };
        for mesh in meshes {
            mesh.parts.iter().for_each(|part| surface.add_part(part, mesh.floor_y));
        }
        surface
    }

    fn add_part(&mut self, part: &MeshPart, floor_y: f64) {
        for face in 0..part.faces.len() {
            let triangle = part.triangle(face).map(|v| Vec3::new(v.x, v.y - floor_y, v.z));
            if let Some(layer) = layer_of(&triangle, part.class_of(face)) {
                self.sample(&triangle, layer);
            }
        }
    }

    fn sample(&mut self, triangle: &[Vec3; 3], layer: Layer) {
        let spacing = self.spec.cell / 2.0;
        for point in triangle_samples(triangle, spacing).filter(|p| p.y < layer.below()) {
            let Some(cell) = self.spec.locate(point.plan()) else { continue };
            match layer {
                Layer::Floor { .. } => self.floor[cell] = keep_lowest(self.floor[cell], point.y as f32),
                Layer::Furniture => self.furniture[cell] = keep_highest(self.furniture[cell], point.y as f32),
            }
        }
    }

    pub fn spec(&self) -> &GridSpec {
        &self.spec
    }

    pub fn floor_height(&self, cell: CellIndex) -> Option<f64> {
        let h = self.floor[cell];
        (!h.is_nan()).then_some(f64::from(h))
    }

    /// Median floor height of the cell and its eight neighbours, which suppresses single-cell noise.
    pub fn smoothed_height(&self, point: Vec2) -> Option<f64> {
        let cell = self.spec.locate(point)?;
        let (ix, iy) = self.spec.coords(cell);
        let mut heights: Vec<f64> = neighbourhood(ix, iy, &self.spec).filter_map(|c| self.floor_height(c)).collect();
        if heights.len() < 3 {
            return None;
        }
        heights.sort_by(f64::total_cmp);
        Some(heights[heights.len() / 2])
    }

    /// Cells where table or seat geometry stands more than 8 in above the floor and below 27 in.
    pub fn furniture_cells(&self) -> impl Iterator<Item = CellIndex> + '_ {
        (0..self.spec.len()).filter(|&cell| {
            let top = self.furniture[cell];
            !top.is_nan() && f64::from(top) - self.floor_height(cell).unwrap_or(0.0) > OBSTACLE_RISE
        })
    }

    /// The floor plane over `area`, or `None` when the mesh saw too little of that floor.
    pub fn plane_in(&self, area: &OrientedBox2) -> Option<FloorPlane> {
        let cells: Vec<CellIndex> =
            self.spec.cells_in(area.bounds()).filter(|&c| area.contains(self.spec.center(c))).collect();
        self.plane_over(&cells)
    }

    /// The floor plane over the given cells, or `None` when the mesh saw too few of them.
    pub fn plane_over(&self, cells: &[CellIndex]) -> Option<FloorPlane> {
        let samples: Vec<(Vec2, f64)> =
            cells.iter().filter_map(|&c| Some((self.spec.center(c), self.floor_height(c)?))).collect();
        let needed = MIN_SAMPLES.max((cells.len() as f64 * MIN_COVERAGE).ceil() as usize);
        if samples.len() < needed {
            return None;
        }
        fit_plane(&samples).map(|gradient| FloorPlane { gradient, samples: samples.len() })
    }

    /// The largest height difference between floor samples within 10 cm of each other along a path
    /// (the mesh smears a step over a few centimetres).
    pub fn level_change_along(&self, points: &[Vec2]) -> Option<LevelChange> {
        let heights: Vec<(Vec2, f64)> = points.iter().filter_map(|&p| Some((p, self.smoothed_height(p)?))).collect();
        if heights.len() < 2 {
            return None;
        }
        let steps = heights.iter().enumerate().flat_map(|(i, a)| {
            let nearby = heights[i + 1..].iter().take_while(move |b| a.0.distance(b.0) <= LEVEL_CHANGE_WINDOW);
            nearby.map(move |b| LevelChange { height: (b.1 - a.1).abs(), at: a.0.lerp(b.0, 0.5) })
        });
        let flat = LevelChange { height: 0.0, at: heights[0].0 };
        Some(steps.fold(flat, |best, step| if step.height > best.height { step } else { best }))
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum Layer {
    Floor { below: f64 },
    Furniture,
}

impl Layer {
    fn below(self) -> f64 {
        match self {
            Layer::Floor { below } => below,
            Layer::Furniture => BLOCKS_FLOOR_BELOW,
        }
    }
}

fn layer_of(triangle: &[Vec3; 3], class: MeshClass) -> Option<Layer> {
    match class {
        MeshClass::Table | MeshClass::Seat => Some(Layer::Furniture),
        MeshClass::Floor if faces_up(triangle) => Some(Layer::Floor { below: MAX_FLOOR_HEIGHT }),
        MeshClass::None if faces_up(triangle) => Some(Layer::Floor { below: MAX_UNCLASSIFIED_FLOOR_HEIGHT }),
        _ => None,
    }
}

fn faces_up(triangle: &[Vec3; 3]) -> bool {
    let normal = (triangle[1] - triangle[0]).cross(triangle[2] - triangle[0]);
    let length = normal.length();
    length > 0.0 && (normal.y / length).abs() >= WALKABLE_NORMAL_Y
}

fn keep_lowest(current: f32, new: f32) -> f32 {
    if current.is_nan() { new } else { current.min(new) }
}

fn keep_highest(current: f32, new: f32) -> f32 {
    if current.is_nan() { new } else { current.max(new) }
}

/// Points on a regular barycentric lattice over the triangle, no further apart than `spacing`.
fn triangle_samples(triangle: &[Vec3; 3], spacing: f64) -> impl Iterator<Item = Vec3> + '_ {
    let [a, b, c] = *triangle;
    let longest = a.distance(b).max(b.distance(c)).max(c.distance(a));
    let steps = ((longest / spacing).ceil() as usize).clamp(1, 400);
    let n = steps as f64;
    (0..=steps).flat_map(move |i| (0..=steps - i).map(move |j| a + (b - a) * (i as f64 / n) + (c - a) * (j as f64 / n)))
}

fn neighbourhood(ix: usize, iy: usize, spec: &GridSpec) -> impl Iterator<Item = CellIndex> + '_ {
    let xs = ix.saturating_sub(1)..=(ix + 1).min(spec.nx - 1);
    let ys = iy.saturating_sub(1)..=(iy + 1).min(spec.ny - 1);
    ys.flat_map(move |y| xs.clone().map(move |x| spec.index(x, y)))
}

/// Gradient of the least-squares plane h = a + g·p through the samples.
fn fit_plane(samples: &[(Vec2, f64)]) -> Option<Vec2> {
    let n = samples.len() as f64;
    let mean_p = samples.iter().fold(Vec2::ZERO, |acc, (p, _)| acc + *p) * (1.0 / n);
    let mean_h = samples.iter().map(|(_, h)| h).sum::<f64>() / n;
    let (mut sxx, mut sxy, mut syy, mut sxh, mut syh) = (0.0, 0.0, 0.0, 0.0, 0.0);
    for (p, h) in samples {
        let (dx, dy, dh) = (p.x - mean_p.x, p.y - mean_p.y, h - mean_h);
        sxx += dx * dx;
        sxy += dx * dy;
        syy += dy * dy;
        sxh += dx * dh;
        syh += dy * dh;
    }
    let det = sxx * syy - sxy * sxy;
    if det.abs() < 1e-12 {
        return None;
    }
    Some(Vec2::new((sxh * syy - syh * sxy) / det, (syh * sxx - sxh * sxy) / det))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::Bounds2;
    use crate::mesh::format::tests::{IDENTITY, floor_patch};

    fn spec() -> GridSpec {
        GridSpec::covering(Bounds2 { min: Vec2::new(-1.0, -1.0), max: Vec2::new(5.0, 5.0) }, 0.025)
    }

    /// A 4 m square floor at world height `floor_y`, rising `slope` metres per metre along +X.
    fn sloped_floor(floor_y: f64, slope: f64) -> ScanMesh {
        let mut part = floor_patch(Vec3::new(2.0, floor_y, 2.0), 4.0, MeshClass::Floor);
        part.vertices.iter_mut().for_each(|v| v.y += slope * v.x);
        ScanMesh { floor_y, parts: vec![part] }
    }

    #[test]
    fn plane_fit_recovers_a_one_in_twenty_slope() {
        let mesh = sloped_floor(-1.3, 0.05);
        let surface = FloorSurface::build(spec(), &[&mesh]);
        let plane = surface.plane_in(&OrientedBox2::new(Vec2::new(1.0, 1.0), 1.2, 1.2, 0.0)).unwrap();
        assert!((plane.slope() - 0.05).abs() < 1e-3, "{plane:?}");
        assert!((plane.slope_along(Vec2::new(1.0, 0.0)) - 0.05).abs() < 1e-3);
        assert!(plane.slope_along(Vec2::new(0.0, 1.0)) < 1e-3);
    }

    #[test]
    fn unseen_floor_gives_no_plane() {
        let surface = FloorSurface::build(spec(), &[&sloped_floor(0.0, 0.0)]);
        assert!(surface.plane_in(&OrientedBox2::new(Vec2::new(4.6, 4.6), 1.0, 1.0, 0.0)).is_none());
        assert!(surface.plane_in(&OrientedBox2::new(Vec2::new(2.0, 2.0), 1.0, 1.0, 0.3)).is_some());
    }

    #[test]
    fn a_half_inch_step_shows_as_a_level_change() {
        let low = floor_patch(Vec3::new(1.0, 0.0, 1.0), 2.0, MeshClass::Floor);
        let high = floor_patch(Vec3::new(3.0, 0.0127, 1.0), 2.0, MeshClass::Floor);
        let mesh = ScanMesh { floor_y: 0.0, parts: vec![low, high] };
        let surface = FloorSurface::build(spec(), &[&mesh]);
        let path: Vec<Vec2> = (0..120).map(|i| Vec2::new(0.5 + i as f64 * 0.025, 1.0)).collect();
        let change = surface.level_change_along(&path).unwrap();
        assert!((change.height - 0.0127).abs() < 1e-4, "{change:?}");
        assert!((change.at.x - 2.0).abs() < 0.06);
        let flat: Vec<Vec2> = path.iter().map(|p| Vec2::new(p.x - 0.4, p.y)).take(40).collect();
        assert!(surface.level_change_along(&flat).unwrap().height < 1e-6);
    }

    #[test]
    fn seats_below_twenty_seven_inches_are_furniture_cells_but_table_tops_are_not() {
        let floor = floor_patch(Vec3::new(2.0, 0.0, 2.0), 4.0, MeshClass::Floor);
        let seat = floor_patch(Vec3::new(1.0, 0.45, 1.0), 0.4, MeshClass::Seat);
        let table_top = floor_patch(Vec3::new(3.0, 0.75, 3.0), 0.8, MeshClass::Table);
        let mesh = ScanMesh { floor_y: 0.0, parts: vec![floor, seat, table_top] };
        let surface = FloorSurface::build(spec(), &[&mesh]);
        let cells: Vec<Vec2> = surface.furniture_cells().map(|c| surface.spec().center(c)).collect();
        assert!(!cells.is_empty());
        let far: Vec<_> = cells.iter().filter(|p| p.distance(Vec2::new(1.0, 1.0)) >= 0.32).collect();
        assert!(far.is_empty(), "{:?}", &far[..far.len().min(5)]);
    }

    #[test]
    fn steep_unclassified_faces_are_not_floor() {
        let mut wall = floor_patch(Vec3::new(2.0, 0.0, 2.0), 1.0, MeshClass::None);
        wall.vertices.iter_mut().for_each(|v| (v.y, v.z) = (v.z - 1.5, 2.0));
        let mesh = ScanMesh { floor_y: 0.0, parts: vec![wall] };
        let surface = FloorSurface::build(spec(), &[&mesh]);
        assert!((0..surface.spec().len()).all(|c| surface.floor_height(c).is_none()));
        assert_eq!(IDENTITY[0], 1.0);
    }
}
