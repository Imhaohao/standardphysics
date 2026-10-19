use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::ops::{Add, Mul, Neg, Sub};

#[derive(Debug, Clone, Copy, PartialEq, Default, Serialize, Deserialize, JsonSchema)]
pub struct Vec2 {
    pub x: f64,
    pub y: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Default, Serialize, Deserialize, JsonSchema)]
pub struct Vec3 {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

impl Vec2 {
    pub const ZERO: Vec2 = Vec2 { x: 0.0, y: 0.0 };

    pub const fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }

    pub fn dot(self, other: Vec2) -> f64 {
        self.x * other.x + self.y * other.y
    }

    pub fn cross(self, other: Vec2) -> f64 {
        self.x * other.y - self.y * other.x
    }

    pub fn length(self) -> f64 {
        self.dot(self).sqrt()
    }

    pub fn distance(self, other: Vec2) -> f64 {
        (self - other).length()
    }

    pub fn normalized(self) -> Vec2 {
        let len = self.length();
        if len == 0.0 { self } else { self * (1.0 / len) }
    }

    pub fn perpendicular(self) -> Vec2 {
        Vec2::new(-self.y, self.x)
    }

    pub fn lerp(self, other: Vec2, t: f64) -> Vec2 {
        self + (other - self) * t
    }
}

impl Vec3 {
    pub const ZERO: Vec3 = Vec3 { x: 0.0, y: 0.0, z: 0.0 };

    pub const fn new(x: f64, y: f64, z: f64) -> Self {
        Self { x, y, z }
    }

    /// The plan position (world X, world Z).
    pub fn plan(self) -> Vec2 {
        Vec2::new(self.x, self.z)
    }

    pub fn distance(self, other: Vec3) -> f64 {
        (self - other).length()
    }

    pub fn length(self) -> f64 {
        (self.x * self.x + self.y * self.y + self.z * self.z).sqrt()
    }

    pub fn cross(self, other: Vec3) -> Vec3 {
        Vec3::new(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )
    }
}

impl Add for Vec3 {
    type Output = Vec3;
    fn add(self, rhs: Vec3) -> Vec3 {
        Vec3::new(self.x + rhs.x, self.y + rhs.y, self.z + rhs.z)
    }
}

impl Sub for Vec3 {
    type Output = Vec3;
    fn sub(self, rhs: Vec3) -> Vec3 {
        Vec3::new(self.x - rhs.x, self.y - rhs.y, self.z - rhs.z)
    }
}

impl Mul<f64> for Vec3 {
    type Output = Vec3;
    fn mul(self, rhs: f64) -> Vec3 {
        Vec3::new(self.x * rhs, self.y * rhs, self.z * rhs)
    }
}

/// Plan directions of an object's local X (width) and Z (depth) axes for a rotation of `yaw`
/// radians about +Y (right-handed): local X maps to (cos, -sin), local Z to (sin, cos).
pub fn yaw_axes(yaw: f64) -> (Vec2, Vec2) {
    let (sin, cos) = yaw.sin_cos();
    (Vec2::new(cos, -sin), Vec2::new(sin, cos))
}

impl Add for Vec2 {
    type Output = Vec2;
    fn add(self, rhs: Vec2) -> Vec2 {
        Vec2::new(self.x + rhs.x, self.y + rhs.y)
    }
}

impl Sub for Vec2 {
    type Output = Vec2;
    fn sub(self, rhs: Vec2) -> Vec2 {
        Vec2::new(self.x - rhs.x, self.y - rhs.y)
    }
}

impl Mul<f64> for Vec2 {
    type Output = Vec2;
    fn mul(self, rhs: f64) -> Vec2 {
        Vec2::new(self.x * rhs, self.y * rhs)
    }
}

impl Neg for Vec2 {
    type Output = Vec2;
    fn neg(self) -> Vec2 {
        Vec2::new(-self.x, -self.y)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f64::consts::FRAC_PI_2;

    #[test]
    fn yaw_quarter_turn_maps_local_x_to_negative_world_z() {
        let (x_axis, z_axis) = yaw_axes(FRAC_PI_2);
        assert!((x_axis.x).abs() < 1e-12 && (x_axis.y + 1.0).abs() < 1e-12);
        assert!((z_axis.x - 1.0).abs() < 1e-12 && z_axis.y.abs() < 1e-12);
    }

    #[test]
    fn perpendicular_is_orthogonal() {
        let v = Vec2::new(3.0, 4.0);
        assert_eq!(v.dot(v.perpendicular()), 0.0);
        assert_eq!(v.length(), 5.0);
    }
}
