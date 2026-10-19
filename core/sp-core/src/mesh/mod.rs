//! The LiDAR scan mesh saved beside each RoomPlan capture, and the floor evidence drawn from it.

mod format;
mod surface;

pub use format::{MeshClass, MeshError, MeshPart, ScanMesh};
pub use surface::{FloorPlane, FloorSurface, HEIGHT_NOISE, LevelChange, SLOPE_NOISE};
