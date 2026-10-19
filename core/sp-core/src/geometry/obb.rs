use super::{Bounds2, Vec2, yaw_axes};

/// A rectangle in plan, rotated by `yaw` about its centre. `half_extents.x` runs along the local X
/// (width) axis, `half_extents.y` along local Z (depth).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct OrientedBox2 {
    pub center: Vec2,
    pub half_extents: Vec2,
    pub yaw: f64,
}

impl OrientedBox2 {
    pub fn new(center: Vec2, width: f64, depth: f64, yaw: f64) -> Self {
        Self { center, half_extents: Vec2::new(width / 2.0, depth / 2.0), yaw }
    }

    pub fn axes(&self) -> (Vec2, Vec2) {
        yaw_axes(self.yaw)
    }

    /// Coordinates of `point` in the box's local frame (x along width, y along depth).
    pub fn to_local(&self, point: Vec2) -> Vec2 {
        let (ax, az) = self.axes();
        let offset = point - self.center;
        Vec2::new(offset.dot(ax), offset.dot(az))
    }

    pub fn from_local(&self, local: Vec2) -> Vec2 {
        let (ax, az) = self.axes();
        self.center + ax * local.x + az * local.y
    }

    pub fn contains(&self, point: Vec2) -> bool {
        let local = self.to_local(point);
        local.x.abs() <= self.half_extents.x && local.y.abs() <= self.half_extents.y
    }

    /// Distance from `point` to the box (0 inside).
    pub fn distance_to(&self, point: Vec2) -> f64 {
        let local = self.to_local(point);
        let dx = (local.x.abs() - self.half_extents.x).max(0.0);
        let dy = (local.y.abs() - self.half_extents.y).max(0.0);
        dx.hypot(dy)
    }

    pub fn corners(&self) -> [Vec2; 4] {
        let h = self.half_extents;
        [
            self.from_local(Vec2::new(-h.x, -h.y)),
            self.from_local(Vec2::new(h.x, -h.y)),
            self.from_local(Vec2::new(h.x, h.y)),
            self.from_local(Vec2::new(-h.x, h.y)),
        ]
    }

    pub fn bounds(&self) -> Bounds2 {
        Bounds2::around(&self.corners())
    }

    pub fn grown(&self, margin: f64) -> Self {
        Self { half_extents: Vec2::new(self.half_extents.x + margin, self.half_extents.y + margin), ..*self }
    }

    /// Separating-axis test against another box.
    pub fn overlaps(&self, other: &OrientedBox2) -> bool {
        let (a1, a2) = self.axes();
        let (b1, b2) = other.axes();
        [a1, a2, b1, b2].iter().all(|axis| {
            let (lo_a, hi_a) = self.project_onto(*axis);
            let (lo_b, hi_b) = other.project_onto(*axis);
            lo_a <= hi_b && lo_b <= hi_a
        })
    }

    fn project_onto(&self, axis: Vec2) -> (f64, f64) {
        self.corners()
            .iter()
            .map(|c| c.dot(axis))
            .fold((f64::INFINITY, f64::NEG_INFINITY), |(lo, hi), v| (lo.min(v), hi.max(v)))
    }

    /// Points along the boundary, at most `spacing` apart.
    pub fn boundary_points(&self, spacing: f64) -> Vec<Vec2> {
        let corners = self.corners();
        (0..4).flat_map(|i| crate::geometry::Segment2::new(corners[i], corners[(i + 1) % 4]).samples(spacing)).collect()
    }

    pub fn width(&self) -> f64 {
        self.half_extents.x * 2.0
    }

    pub fn depth(&self) -> f64 {
        self.half_extents.y * 2.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f64::consts::FRAC_PI_4;

    #[test]
    fn rotated_box_contains_and_distance() {
        let b = OrientedBox2::new(Vec2::new(1.0, 1.0), 2.0, 1.0, FRAC_PI_4);
        assert!(b.contains(Vec2::new(1.0, 1.0)));
        let far = b.from_local(Vec2::new(1.0 + 0.3, 0.0));
        assert!((b.distance_to(far) - 0.3).abs() < 1e-9);
        assert!(!b.contains(far));
    }

    #[test]
    fn overlap_by_separating_axes() {
        let a = OrientedBox2::new(Vec2::new(0.0, 0.0), 2.0, 2.0, 0.0);
        let b = OrientedBox2::new(Vec2::new(2.3, 0.0), 2.0, 2.0, FRAC_PI_4);
        assert!(a.overlaps(&b));
        let c = OrientedBox2::new(Vec2::new(2.5, 0.0), 2.0, 2.0, 0.0);
        assert!(!a.overlaps(&c));
    }

    #[test]
    fn corners_round_trip_through_local_frame() {
        let b = OrientedBox2::new(Vec2::new(-2.0, 3.0), 1.2, 0.6, 0.7);
        for corner in b.corners() {
            let local = b.to_local(corner);
            assert!((local.x.abs() - 0.6).abs() < 1e-9 && (local.y.abs() - 0.3).abs() < 1e-9);
        }
    }
}
