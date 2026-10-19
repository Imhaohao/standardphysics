//! RoomPlan vocabulary to Scene vocabulary.

use crate::scene::RoomKind;

/// Scene object category (an id from `rules/metrics.json` `object_categories`) for a RoomPlan
/// `CapturedRoom.Object.Category` case and its attributes. RoomPlan classes keep their catalog id
/// (`washerDryer` becomes `washer_dryer`); a dining table is refined to the detector category.
pub fn object_category(roomplan_case: &str, attributes: &[(String, String)]) -> String {
    let is_dining_table = roomplan_case == "table" && attributes.iter().any(|(k, v)| k == "TableType" && v == "dining");
    if is_dining_table { "dining_table".to_string() } else { snake_case(roomplan_case) }
}

pub fn snake_case(camel: &str) -> String {
    let mut out = String::with_capacity(camel.len() + 4);
    for ch in camel.chars() {
        if ch.is_ascii_uppercase() && !out.is_empty() {
            out.push('_');
        }
        out.push(ch.to_ascii_lowercase());
    }
    out
}

/// Room kind for a RoomPlan section label (iOS 17 `CapturedRoom.Section.Label`).
pub fn room_kind(section_label: &str) -> RoomKind {
    match section_label {
        "bathroom" => RoomKind::Restroom,
        "kitchen" => RoomKind::Kitchen,
        "diningRoom" => RoomKind::Restaurant,
        "hallway" | "corridor" => RoomKind::Corridor,
        "office" | "study" => RoomKind::Office,
        "storage" | "closet" | "laundryRoom" => RoomKind::Storage,
        _ => RoomKind::Other,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn categories_refine_by_attribute() {
        let attrs = vec![("TableType".to_string(), "dining".to_string())];
        assert_eq!(object_category("table", &attrs), "dining_table");
        assert_eq!(object_category("table", &[]), "table");
        assert_eq!(object_category("storage", &[("StorageType".into(), "shelf".into())]), "storage");
        assert_eq!(object_category("washerDryer", &[]), "washer_dryer");
        assert_eq!(object_category("toilet", &[]), "toilet");
    }

    #[test]
    fn section_labels_map_to_room_kinds() {
        assert_eq!(room_kind("bathroom"), RoomKind::Restroom);
        assert_eq!(room_kind("livingRoom"), RoomKind::Other);
    }

    #[test]
    fn snake_case_splits_humps() {
        assert_eq!(snake_case("livingRoom"), "living_room");
    }
}
