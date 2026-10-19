//! Accessible-route analysis on a storey's clearance field: widest (bottleneck) paths from entrances,
//! clear width along a route, pinch points, passing spaces, 180-degree turns and turning spaces.

mod field;
mod leg;
mod shortest;
mod turning;
mod widest;

pub use field::{DOOR_MIN_CLEAR_WIDTH, EXEMPT, RouteField};
pub use leg::{Pinch, RouteLeg, Turn180, trace_leg};
pub use shortest::ShortestTree;
pub use turning::{largest_turning_circle, t_turn_fits};
pub use widest::WidestTree;

/// 36 in: minimum clear width of an accessible route (403.5.1).
pub const ROUTE_MIN_CLEAR_WIDTH: f64 = 0.9144;
/// 60 in: width at which two wheelchairs can pass (403.5.3) and the turning-circle diameter (304.3.1).
pub const PASSING_WIDTH: f64 = 1.524;
