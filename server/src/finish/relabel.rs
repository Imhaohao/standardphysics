//! RoomPlan reports ordering counters as `storage` (imported as `table`) and built-in benches as
//! `sofa` or `chair`, so the wrong rules run on them. The phone sends a crop of each doubtful
//! object as `{"id", "relabel_object_id", "crop_artifact_id"}`; at finish the vision model picks
//! from a short list of categories. A confident answer replaces the category; otherwise the owner
//! is asked through `object.category_override`.

use std::collections::{BTreeMap, HashMap};

use anyhow::Result;
use serde_json::{json, Value};
use uuid::Uuid;

use super::labelling::{crop_artifact_id, crop_locations, is_relabel, label_with_cache};
use crate::engine::{category_choices, ScannedObject, CATEGORY_OVERRIDE_METRIC};
use crate::findings::{needs_info_finding, Ask, Finding, Point3};
use crate::live::rooms::RoomState;
use crate::state::AppState;
use crate::vision::{LabelQuestion, LabelRequest, LabelResult};

pub const RELABEL_CATEGORIES: &[&str] = &[
    "counter",
    "service_counter",
    "sales_counter",
    "bar_counter",
    "work_surface",
    "dining_table",
    "table",
    "storage",
    "shelf",
    "display_rack",
    "bench",
    "sofa",
    "chair",
    "kiosk",
];

/// A vision answer below this confidence goes to the owner instead.
pub const CONFIDENT: f64 = 0.6;

const METRES_TO_INCHES: f64 = 39.370_078_740_157_48;

#[derive(Debug, Clone, PartialEq)]
pub struct RelabelItem {
    pub room_id: String,
    pub observation_id: String,
    pub object_id: String,
    pub crop_artifact_id: Option<Uuid>,
}

/// What the label stage did with relabel requests.
#[derive(Debug, Default, PartialEq, Eq)]
pub struct RelabelOutcome {
    /// Objects whose category the model settled.
    pub applied: u32,
    /// Observations that changed and need saving (confident or not).
    pub changed: u32,
}

fn relabel_categories() -> Vec<String> {
    RELABEL_CATEGORIES.iter().map(|c| c.to_string()).collect()
}

fn relabel_item(room_id: &str, id: &str, observation: &Value) -> Option<RelabelItem> {
    Some(RelabelItem {
        room_id: room_id.to_string(),
        observation_id: id.to_string(),
        object_id: observation.get("relabel_object_id")?.as_str()?.to_string(),
        crop_artifact_id: crop_artifact_id(observation),
    })
}

pub fn relabel_items(rooms: &[RoomState]) -> Vec<RelabelItem> {
    rooms
        .iter()
        .flat_map(|room| {
            room.observations
                .iter()
                .filter(|(_, o)| is_relabel(o))
                .filter_map(|(id, o)| relabel_item(&room.room_id, id, o))
        })
        .collect()
}

fn is_settled(observation: &Value) -> bool {
    observation.get("relabel_category").is_some()
}

fn humanize(category: &str) -> String {
    category.replace('_', " ")
}

fn inches(metres: f64) -> i64 {
    (metres * METRES_TO_INCHES).round() as i64
}

/// What the scanner saw, told to the model so it can weigh the photo against it.
pub fn scanner_context(object: &ScannedObject) -> String {
    format!(
        "The scanner called it {}. Its top is {} in above the floor and it is {} in wide.",
        humanize(&object.category),
        inches(object.top_height),
        inches(object.width)
    )
}

/// The crops of every relabel request that has one, ready for the model.
pub struct RelabelJobs {
    requests: Vec<LabelRequest>,
}

pub async fn prepare(
    state: &AppState,
    scan_id: Uuid,
    rooms: &[RoomState],
    scanned: &BTreeMap<String, ScannedObject>,
) -> Result<RelabelJobs> {
    let items: Vec<RelabelItem> = relabel_items(rooms)
        .into_iter()
        .filter(|item| scanned.contains_key(&item.object_id))
        .collect();
    let crop_ids = items.iter().filter_map(|i| i.crop_artifact_id).collect();
    let locations = crop_locations(&state.db, scan_id, crop_ids).await?;
    let requests = items
        .iter()
        .filter_map(|item| {
            let crop = locations.get(&item.crop_artifact_id?)?;
            Some(LabelRequest {
                observation_id: item.observation_id.clone(),
                crop_key: crop.key.clone(),
                content_type: crop.content_type.clone(),
                image_sha256: crop.sha256.clone(),
                context: scanner_context(&scanned[&item.object_id]),
            })
        })
        .collect();
    Ok(RelabelJobs { requests })
}

pub async fn fetch(
    state: &AppState,
    scan_id: Uuid,
    jobs: RelabelJobs,
) -> Result<HashMap<String, LabelResult>> {
    if jobs.requests.is_empty() {
        return Ok(HashMap::new());
    }
    let categories = relabel_categories();
    label_with_cache(
        state,
        scan_id,
        LabelQuestion::Relabel,
        &categories,
        jobs.requests,
    )
    .await
}

fn record_result(observation: &mut Value, result: &LabelResult) -> bool {
    observation["label_confidence"] = json!(result.confidence);
    observation["label_source"] = json!("vision");
    if let Some(built_in) = result.built_in {
        observation["built_in"] = json!(built_in);
    }
    if result.confidence < CONFIDENT {
        observation["relabel_suggestion"] = json!(result.category);
        return false;
    }
    observation["relabel_category"] = json!(result.category);
    true
}

/// Write the model's answers onto the relabel observations, so a re-assessment reuses them.
pub fn apply(rooms: &mut [RoomState], results: &HashMap<String, LabelResult>) -> RelabelOutcome {
    let mut outcome = RelabelOutcome::default();
    for room in rooms {
        for (id, observation) in room.observations.iter_mut() {
            let Some(result) = results.get(id).filter(|_| is_relabel(observation)) else {
                continue;
            };
            outcome.changed += 1;
            outcome.applied += u32::from(record_result(observation, result));
        }
    }
    outcome
}

fn is_answered(answers: &[Value], object_id: &str) -> bool {
    answers.iter().any(|a| {
        a.get("subject_id").and_then(Value::as_str) == Some(object_id)
            && a.get("metric").and_then(Value::as_str) == Some(CATEGORY_OVERRIDE_METRIC)
    })
}

fn question(item: &RelabelItem, object: &ScannedObject) -> Finding {
    let scanned = humanize(&object.category);
    let top = inches(object.top_height);
    let [x, y, z] = object.center;
    Finding {
        title: "Check what this object is".to_string(),
        room_id: Some(item.room_id.clone()),
        location: Some(Point3 { x, y, z }),
        ask: Some(Ask {
            subject_id: item.object_id.clone(),
            metric: CATEGORY_OVERRIDE_METRIC.to_string(),
            prompt: format!("The scan saw a {scanned} about {top} in high here. What is it?"),
            value_type: "enum".to_string(),
            unit: String::new(),
            options: category_choices(),
            photo: false,
        }),
        ..needs_info_finding(
            "label.category_check",
            &item.object_id,
            &format!(
                "The scan says this is a {scanned}, but counters and built-in seating are often \
                 scanned this way and have their own rules. Say what it is so the right rules run."
            ),
        )
    }
}

/// One owner question for each relabel the model did not settle and the owner has not answered.
pub fn questions(
    rooms: &[RoomState],
    answers: &[Value],
    scanned: &BTreeMap<String, ScannedObject>,
) -> Vec<Finding> {
    let unsettled = rooms.iter().flat_map(|room| {
        room.observations
            .iter()
            .filter(|(_, o)| is_relabel(o) && !is_settled(o))
            .filter_map(|(id, o)| relabel_item(&room.room_id, id, o))
    });
    let mut asked = std::collections::BTreeSet::new();
    unsettled
        .filter(|item| !is_answered(answers, &item.object_id))
        .filter(|item| asked.insert(item.object_id.clone()))
        .filter_map(|item| Some(question(&item, scanned.get(&item.object_id)?)))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scanned() -> BTreeMap<String, ScannedObject> {
        BTreeMap::from([(
            "OBJ".to_string(),
            ScannedObject {
                room_id: "r1".into(),
                category: "storage".into(),
                top_height: 0.9652,
                width: 1.8288,
                center: [1.0, 0.48, 1.0],
            },
        )])
    }

    fn room(observation: Value) -> RoomState {
        let mut room = RoomState::new("r1");
        room.observations.insert("relabel-OBJ".into(), observation);
        room
    }

    fn result(category: &str, confidence: f64) -> HashMap<String, LabelResult> {
        HashMap::from([(
            "relabel-OBJ".to_string(),
            LabelResult {
                observation_id: "relabel-OBJ".into(),
                category: category.into(),
                confidence,
                built_in: Some(true),
            },
        )])
    }

    #[test]
    fn the_scanner_context_is_in_inches() {
        assert_eq!(
            scanner_context(&scanned()["OBJ"]),
            "The scanner called it storage. Its top is 38 in above the floor and it is 72 in wide."
        );
    }

    #[test]
    fn a_confident_answer_settles_the_object() {
        let mut rooms = vec![room(
            json!({"id": "relabel-OBJ", "relabel_object_id": "OBJ"}),
        )];
        let outcome = apply(&mut rooms, &result("sales_counter", 0.9));
        assert_eq!(
            outcome,
            RelabelOutcome {
                applied: 1,
                changed: 1
            }
        );
        let observation = &rooms[0].observations["relabel-OBJ"];
        assert_eq!(observation["relabel_category"], "sales_counter");
        assert_eq!(observation["built_in"], true);
        assert!(questions(&rooms, &[], &scanned()).is_empty());
    }

    #[test]
    fn an_unsure_answer_asks_the_owner_until_answered() {
        let mut rooms = vec![room(
            json!({"id": "relabel-OBJ", "relabel_object_id": "OBJ"}),
        )];
        let outcome = apply(&mut rooms, &result("sales_counter", 0.4));
        assert_eq!(
            outcome,
            RelabelOutcome {
                applied: 0,
                changed: 1
            }
        );
        let asked = questions(&rooms, &[], &scanned());
        assert_eq!(asked.len(), 1);
        let ask = asked[0].ask.as_ref().unwrap();
        assert_eq!(ask.metric, CATEGORY_OVERRIDE_METRIC);
        assert_eq!(ask.subject_id, "OBJ");
        assert_eq!(ask.value_type, "enum");
        assert!(ask.options.contains(&"Something else".to_string()));
        let answer = json!({"subject_id": "OBJ", "metric": CATEGORY_OVERRIDE_METRIC, "value": "Something else"});
        assert!(questions(&rooms, &[answer], &scanned()).is_empty());
    }

    #[test]
    fn objects_missing_from_the_scan_are_not_asked_about() {
        let rooms = vec![room(
            json!({"id": "relabel-OBJ", "relabel_object_id": "GONE"}),
        )];
        assert!(questions(&rooms, &[], &scanned()).is_empty());
    }
}
