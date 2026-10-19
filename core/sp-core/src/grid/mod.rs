//! Occupancy grids over a storey's floor plan and the distance fields derived from them.

mod edt;
pub(crate) mod occupancy;
mod probe;
mod spec;

pub use edt::{ClearanceField, squared_distance_transform};
pub use occupancy::{BLOCKS_FLOOR_BELOW, CellState, DoorGap, GridOptions, NONE, OccupancyGrid, blocks_floor, door_gap, is_zone_category};
pub use probe::{Extent, Probe, area_is_free};
pub use spec::{CellIndex, GridSpec};
