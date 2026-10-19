//! Plan (XZ) and 3D primitives. Plan coordinates use `Vec2 { x, y }` where `y` is world Z.

mod obb;
mod polygon;
mod segment;
mod vec;

pub use obb::OrientedBox2;
pub use polygon::{Bounds2, Polygon2};
pub use segment::Segment2;
pub use vec::{Vec2, Vec3, yaw_axes};
