//! Owner corrections to what an object is. RoomPlan reports ordering counters as `storage` and
//! built-in benches as `sofa`, so the owner can answer `object.category_override` on an object
//! and every rule then sees the corrected category.

use crate::scene::{Object, Observation, ObservationValue, Room, Scene};

pub const CATEGORY_OVERRIDE_METRIC: &str = "object.category_override";

/// One answer the owner can pick, and the category it stands for (`None` keeps the scanned one).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CategoryChoice {
    pub label: &'static str,
    pub category: Option<&'static str>,
    pub built_in: Option<bool>,
}

pub const CATEGORY_CHOICES: &[CategoryChoice] = &[
    CategoryChoice { label: "A counter where customers order or pay", category: Some("sales_counter"), built_in: None },
    CategoryChoice { label: "A table people sit at", category: Some("dining_table"), built_in: None },
    CategoryChoice { label: "Storage or shelving", category: Some("storage"), built_in: None },
    CategoryChoice { label: "A built-in bench", category: Some("bench"), built_in: Some(true) },
    CategoryChoice { label: "Something else", category: None, built_in: None },
];

/// The owner's options, in the order they are offered.
pub fn choice_labels() -> Vec<String> {
    CATEGORY_CHOICES.iter().map(|c| c.label.to_string()).collect()
}

/// What an answer turns the object into.
#[derive(Debug, Clone, PartialEq, Eq)]
struct Correction {
    category: String,
    built_in: Option<bool>,
}

/// One of the offered labels, or a category id given directly. `None` keeps the scanned category.
fn correction_for(answer: &str, is_known_category: &dyn Fn(&str) -> bool) -> Option<Correction> {
    let answer = answer.trim();
    if let Some(choice) = CATEGORY_CHOICES.iter().find(|c| c.label.eq_ignore_ascii_case(answer)) {
        return choice
            .category
            .map(|category| Correction { category: category.to_string(), built_in: choice.built_in });
    }
    is_known_category(answer).then(|| Correction { category: answer.to_string(), built_in: None })
}

fn override_answer(observation: &Observation) -> Option<&str> {
    if observation.metric != CATEGORY_OVERRIDE_METRIC {
        return None;
    }
    match &observation.value {
        ObservationValue::Text(text) => Some(text.as_str()),
        _ => None,
    }
}

fn apply_correction(object: &mut Object, correction: Correction) {
    if object.category != correction.category {
        object.attributes.entry("scanned_category".into()).or_insert_with(|| object.category.clone());
    }
    object.category = correction.category;
    object.attributes.insert("label_source".into(), "owner".into());
    if let Some(built_in) = correction.built_in {
        object.attributes.insert("built_in".into(), built_in.to_string());
    }
}

/// Apply every owner category answer to the objects of `room`. Later answers win.
pub fn apply_to_room(room: &mut Room, observations: &[Observation], is_known_category: &dyn Fn(&str) -> bool) {
    for observation in observations {
        let Some(answer) = override_answer(observation) else {
            continue;
        };
        let Some(object) = room.objects.iter_mut().find(|o| o.id == observation.subject_id) else {
            continue;
        };
        if let Some(correction) = correction_for(answer, is_known_category) {
            apply_correction(object, correction);
        }
    }
}

/// Apply every owner category answer in the scene's observations to its objects.
pub fn apply_category_overrides(scene: &mut Scene, is_known_category: &dyn Fn(&str) -> bool) {
    let observations = std::mem::take(&mut scene.observations);
    for room in &mut scene.rooms {
        apply_to_room(room, &observations, is_known_category);
    }
    scene.observations = observations;
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::{Polygon2, Vec2, Vec3};
    use crate::scene::{ObjectSource, ObservationSource};
    use std::collections::BTreeMap;

    fn known(category: &str) -> bool {
        ["sales_counter", "dining_table", "storage", "bench", "work_surface"].contains(&category)
    }

    fn room_with_storage() -> Room {
        Room {
            id: "r1".into(),
            name: "Shop".into(),
            kind: Default::default(),
            storey: 0,
            floor: Polygon2::rectangle(Vec2::new(0.0, 0.0), Vec2::new(4.0, 3.0)),
            ceiling_height: 2.7,
            walls: vec![],
            openings: vec![],
            objects: vec![Object {
                id: "obj".into(),
                category: "storage".into(),
                center: Vec3::new(1.0, 0.45, 1.0),
                size: Vec3::new(1.8, 0.9, 0.6),
                yaw: 0.0,
                top_height: 0.9,
                confidence: 1.0,
                source: ObjectSource::Roomplan,
                attributes: BTreeMap::new(),
            }],
        }
    }

    fn answer(value: &str) -> Observation {
        Observation {
            id: "owner:obj:object.category_override".into(),
            subject_id: "obj".into(),
            metric: CATEGORY_OVERRIDE_METRIC.into(),
            value: ObservationValue::Text(value.into()),
            unit: None,
            source: ObservationSource::Owner,
            confidence: 1.0,
        }
    }

    #[test]
    fn the_catalog_offers_the_same_choices() {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../rules/metrics.json");
        let catalog = crate::metrics::Catalog::from_json(&std::fs::read_to_string(path).unwrap()).unwrap();
        let metric = catalog.metric(CATEGORY_OVERRIDE_METRIC).expect("override metric is in the catalog");
        assert_eq!(metric.enum_values, choice_labels());
        for category in CATEGORY_CHOICES.iter().filter_map(|c| c.category) {
            assert!(catalog.is_known_category(category), "{category}");
        }
    }

    #[test]
    fn an_offered_choice_changes_the_category() {
        let mut room = room_with_storage();
        apply_to_room(&mut room, &[answer("A counter where customers order or pay")], &known);
        let object = &room.objects[0];
        assert_eq!(object.category, "sales_counter");
        assert_eq!(object.attribute("scanned_category"), Some("storage"));
        assert_eq!(object.attribute("label_source"), Some("owner"));
    }

    #[test]
    fn a_bench_is_recorded_as_built_in() {
        let mut room = room_with_storage();
        apply_to_room(&mut room, &[answer("a built-in bench")], &known);
        assert_eq!(room.objects[0].category, "bench");
        assert_eq!(room.objects[0].attribute("built_in"), Some("true"));
    }

    #[test]
    fn something_else_and_unknown_answers_keep_the_scanned_category() {
        let mut room = room_with_storage();
        apply_to_room(&mut room, &[answer("Something else"), answer("a spaceship")], &known);
        assert_eq!(room.objects[0].category, "storage");
        assert!(room.objects[0].attributes.is_empty());
    }

    #[test]
    fn a_category_id_is_accepted_directly() {
        let mut room = room_with_storage();
        apply_to_room(&mut room, &[answer("work_surface")], &known);
        assert_eq!(room.objects[0].category, "work_surface");
    }

    #[test]
    fn applying_twice_keeps_the_original_scanned_category() {
        let mut scene = Scene { rooms: vec![room_with_storage()], ..Scene::default() };
        scene.observations.push(answer("A table people sit at"));
        apply_category_overrides(&mut scene, &known);
        apply_category_overrides(&mut scene, &known);
        let object = &scene.rooms[0].objects[0];
        assert_eq!(object.category, "dining_table");
        assert_eq!(object.attribute("scanned_category"), Some("storage"));
        assert_eq!(scene.observations.len(), 1);
    }
}
