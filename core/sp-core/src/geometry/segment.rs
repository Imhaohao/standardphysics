use super::Vec2;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Segment2 {
    pub start: Vec2,
    pub end: Vec2,
}

impl Segment2 {
    pub const fn new(start: Vec2, end: Vec2) -> Self {
        Self { start, end }
    }

    pub fn length(&self) -> f64 {
        self.start.distance(self.end)
    }

    pub fn direction(&self) -> Vec2 {
        (self.end - self.start).normalized()
    }

    pub fn midpoint(&self) -> Vec2 {
        self.start.lerp(self.end, 0.5)
    }

    /// Parameter in [0, 1] of the point on the segment closest to `point`.
    pub fn project(&self, point: Vec2) -> f64 {
        let along = self.end - self.start;
        let len_sq = along.dot(along);
        if len_sq == 0.0 {
            return 0.0;
        }
        ((point - self.start).dot(along) / len_sq).clamp(0.0, 1.0)
    }

    pub fn closest_point(&self, point: Vec2) -> Vec2 {
        self.start.lerp(self.end, self.project(point))
    }

    /// Points from start to end inclusive, at most `spacing` apart.
    pub fn samples(&self, spacing: f64) -> Vec<Vec2> {
        let steps = (self.length() / spacing.max(1e-6)).ceil().max(1.0) as usize;
        (0..=steps).map(|i| self.start.lerp(self.end, i as f64 / steps as f64)).collect()
    }

    pub fn distance_to(&self, point: Vec2) -> f64 {
        self.closest_point(point).distance(point)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn distance_to_interior_and_endpoint() {
        let s = Segment2::new(Vec2::new(0.0, 0.0), Vec2::new(2.0, 0.0));
        assert_eq!(s.distance_to(Vec2::new(1.0, 1.5)), 1.5);
        assert_eq!(s.distance_to(Vec2::new(5.0, 4.0)), 5.0);
    }
}
