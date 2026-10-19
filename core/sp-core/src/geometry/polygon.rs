use super::{Segment2, Vec2};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

/// A simple polygon in plan (XZ). Winding may be either direction.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize, JsonSchema)]
pub struct Polygon2 {
    pub points: Vec<Vec2>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Bounds2 {
    pub min: Vec2,
    pub max: Vec2,
}

impl Bounds2 {
    pub const EMPTY: Bounds2 = Bounds2 {
        min: Vec2 { x: f64::INFINITY, y: f64::INFINITY },
        max: Vec2 { x: f64::NEG_INFINITY, y: f64::NEG_INFINITY },
    };

    pub fn around(points: &[Vec2]) -> Self {
        points.iter().fold(Self::EMPTY, |b, p| b.including(*p))
    }

    pub fn including(self, p: Vec2) -> Self {
        Self {
            min: Vec2::new(self.min.x.min(p.x), self.min.y.min(p.y)),
            max: Vec2::new(self.max.x.max(p.x), self.max.y.max(p.y)),
        }
    }

    pub fn union(self, other: Bounds2) -> Self {
        self.including(other.min).including(other.max)
    }

    pub fn is_empty(&self) -> bool {
        self.min.x > self.max.x || self.min.y > self.max.y
    }

    pub fn expanded(self, margin: f64) -> Self {
        Self {
            min: Vec2::new(self.min.x - margin, self.min.y - margin),
            max: Vec2::new(self.max.x + margin, self.max.y + margin),
        }
    }

    pub fn width(&self) -> f64 {
        self.max.x - self.min.x
    }

    pub fn height(&self) -> f64 {
        self.max.y - self.min.y
    }

    pub fn overlaps(&self, other: &Bounds2) -> bool {
        self.min.x <= other.max.x && other.min.x <= self.max.x && self.min.y <= other.max.y && other.min.y <= self.max.y
    }
}

impl Polygon2 {
    pub fn new(points: Vec<Vec2>) -> Self {
        Self { points }
    }

    pub fn rectangle(min: Vec2, max: Vec2) -> Self {
        Self::new(vec![min, Vec2::new(max.x, min.y), max, Vec2::new(min.x, max.y)])
    }

    pub fn is_valid(&self) -> bool {
        self.points.len() >= 3
    }

    pub fn edges(&self) -> impl Iterator<Item = Segment2> + '_ {
        let n = self.points.len();
        (0..n).map(move |i| Segment2::new(self.points[i], self.points[(i + 1) % n]))
    }

    pub fn signed_area(&self) -> f64 {
        self.edges().map(|e| e.start.cross(e.end)).sum::<f64>() / 2.0
    }

    pub fn area(&self) -> f64 {
        self.signed_area().abs()
    }

    pub fn perimeter(&self) -> f64 {
        self.edges().map(|e| e.length()).sum()
    }

    pub fn centroid(&self) -> Vec2 {
        let area = self.signed_area();
        if area.abs() < 1e-12 {
            return self.vertex_mean();
        }
        let sum = self.edges().fold(Vec2::ZERO, |acc, e| {
            let w = e.start.cross(e.end);
            acc + (e.start + e.end) * w
        });
        sum * (1.0 / (6.0 * area))
    }

    fn vertex_mean(&self) -> Vec2 {
        let n = self.points.len().max(1) as f64;
        self.points.iter().fold(Vec2::ZERO, |acc, p| acc + *p) * (1.0 / n)
    }

    pub fn bounds(&self) -> Bounds2 {
        Bounds2::around(&self.points)
    }

    /// Even-odd point-in-polygon test.
    pub fn contains(&self, p: Vec2) -> bool {
        self.edges().filter(|e| crosses_ray(e, p)).count() % 2 == 1
    }

    pub fn distance_to_boundary(&self, p: Vec2) -> f64 {
        self.edges().map(|e| e.distance_to(p)).fold(f64::INFINITY, f64::min)
    }

    /// X coordinates where the horizontal line `y` crosses the boundary, sorted. Used for scanline fill.
    pub fn scanline_crossings(&self, y: f64) -> Vec<f64> {
        let mut xs: Vec<f64> = self
            .edges()
            .filter(|e| (e.start.y <= y) != (e.end.y <= y))
            .map(|e| e.start.x + (y - e.start.y) / (e.end.y - e.start.y) * (e.end.x - e.start.x))
            .collect();
        xs.sort_by(f64::total_cmp);
        xs
    }

    pub fn translated(&self, offset: Vec2) -> Self {
        Self::new(self.points.iter().map(|p| *p + offset).collect())
    }
}

fn crosses_ray(edge: &Segment2, p: Vec2) -> bool {
    let (a, b) = (edge.start, edge.end);
    if (a.y > p.y) == (b.y > p.y) {
        return false;
    }
    let x_at = a.x + (p.y - a.y) / (b.y - a.y) * (b.x - a.x);
    p.x < x_at
}

#[cfg(test)]
mod tests {
    use super::*;

    fn l_shape() -> Polygon2 {
        Polygon2::new(vec![
            Vec2::new(0.0, 0.0),
            Vec2::new(4.0, 0.0),
            Vec2::new(4.0, 1.0),
            Vec2::new(1.0, 1.0),
            Vec2::new(1.0, 3.0),
            Vec2::new(0.0, 3.0),
        ])
    }

    #[test]
    fn l_shape_area_and_containment() {
        let poly = l_shape();
        assert_eq!(poly.area(), 6.0);
        assert!(poly.contains(Vec2::new(0.5, 2.5)));
        assert!(poly.contains(Vec2::new(3.5, 0.5)));
        assert!(!poly.contains(Vec2::new(2.0, 2.0)));
        assert_eq!(poly.perimeter(), 14.0);
    }

    #[test]
    fn rectangle_centroid() {
        let poly = Polygon2::rectangle(Vec2::new(0.0, 0.0), Vec2::new(2.0, 4.0));
        assert_eq!(poly.centroid(), Vec2::new(1.0, 2.0));
    }

    #[test]
    fn scanline_crossings_of_l_shape() {
        assert_eq!(l_shape().scanline_crossings(0.5), vec![0.0, 4.0]);
        assert_eq!(l_shape().scanline_crossings(2.0), vec![0.0, 1.0]);
    }
}
