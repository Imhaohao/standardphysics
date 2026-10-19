//! Extractors grouped by element. Each module lists `(metric id, extractor)` pairs.

mod circulation;
pub(crate) mod clear_floor;
mod door;
mod fixtures;
mod reach;
mod room;
mod route;
mod site;
pub(crate) mod support;
mod toilet;

use super::Extractor;

pub const ALL: &[&[(&str, Extractor)]] = &[
    site::EXTRACTORS,
    room::EXTRACTORS,
    route::EXTRACTORS,
    door::EXTRACTORS,
    clear_floor::EXTRACTORS,
    reach::EXTRACTORS,
    toilet::EXTRACTORS,
    fixtures::EXTRACTORS,
    circulation::EXTRACTORS,
];
