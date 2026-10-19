//! Import Apple RoomPlan `CapturedRoom` / `CapturedStructure` JSON (as produced by `JSONEncoder` on
//! iOS 17+) into the Scene model, and merge separately captured rooms into storeys.

mod categories;
mod convert;
mod merge;
mod raw;

pub use categories::{object_category, room_kind};
pub use convert::{ImportError, import_captured_json, import_room};
pub use merge::{detect_connections, merge_rooms};
pub use raw::{CapturedRoom, CapturedStructure, Transform};
