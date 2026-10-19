use std::collections::HashMap;

use anyhow::Result;
use serde_json::{json, Value};
use sqlx::PgPool;
use uuid::Uuid;

use crate::engine::object_categories;
use crate::live::rooms::RoomState;
use crate::state::AppState;
use crate::vision::{group_by_id, LabelRequest};

#[derive(Debug, Clone)]
pub struct PendingObservation {
    pub room_id: String,
    pub observation_id: String,
    pub crop_artifact_id: Option<Uuid>,
}

#[derive(Debug, Default)]
pub struct LabelStage {
    pub labelled: u32,
    pub unresolved: Vec<PendingObservation>,
}

fn has_category(observation: &Value) -> bool {
    observation
        .get("category")
        .and_then(Value::as_str)
        .is_some_and(|c| !c.is_empty())
}

fn crop_artifact_id(observation: &Value) -> Option<Uuid> {
    observation.get("crop_artifact_id")?.as_str()?.parse().ok()
}

fn needs_label(observation: &Value) -> bool {
    !has_category(observation) && observation.get("metric").is_none()
}

pub fn pending_observations(rooms: &[RoomState]) -> Vec<PendingObservation> {
    rooms
        .iter()
        .flat_map(|room| {
            room.observations
                .iter()
                .filter(|(_, observation)| needs_label(observation))
                .map(|(id, observation)| PendingObservation {
                    room_id: room.room_id.clone(),
                    observation_id: id.clone(),
                    crop_artifact_id: crop_artifact_id(observation),
                })
        })
        .collect()
}

async fn crop_locations(
    db: &PgPool,
    scan_id: Uuid,
    pending: &[PendingObservation],
) -> Result<HashMap<Uuid, (String, String)>> {
    let ids: Vec<Uuid> = pending.iter().filter_map(|p| p.crop_artifact_id).collect();
    if ids.is_empty() {
        return Ok(HashMap::new());
    }
    let rows: Vec<(Uuid, String, String)> = sqlx::query_as(
        "SELECT id, s3_key, content_type FROM artifacts WHERE scan_id = $1 AND id = ANY($2)",
    )
    .bind(scan_id)
    .bind(&ids)
    .fetch_all(db)
    .await?;
    Ok(rows
        .into_iter()
        .map(|(id, key, content_type)| (id, (key, content_type)))
        .collect())
}

fn label_requests(
    pending: &[PendingObservation],
    locations: &HashMap<Uuid, (String, String)>,
) -> Vec<LabelRequest> {
    pending
        .iter()
        .filter_map(|p| {
            let (key, content_type) = locations.get(&p.crop_artifact_id?)?;
            Some(LabelRequest {
                observation_id: p.observation_id.clone(),
                crop_key: key.clone(),
                content_type: content_type.clone(),
            })
        })
        .collect()
}

fn apply_label(observation: &mut Value, category: &str, confidence: f64) {
    observation["category"] = json!(category);
    observation["label_source"] = json!("vision");
    observation["label_confidence"] = json!(confidence);
}

pub async fn run_label_stage(
    state: &AppState,
    scan_id: Uuid,
    rooms: &mut [RoomState],
) -> Result<LabelStage> {
    let pending = pending_observations(rooms);
    if pending.is_empty() {
        return Ok(LabelStage::default());
    }
    let locations = crop_locations(&state.db, scan_id, &pending).await?;
    let requests = label_requests(&pending, &locations);
    let categories = object_categories();
    let outcome = state
        .labeller
        .label_all(&state.storage, categories, requests)
        .await;
    if outcome.deadline_hit {
        tracing::warn!(%scan_id, missing = outcome.unlabelled.len(), "vision labelling hit its deadline");
    }
    let labels = group_by_id(outcome.labelled);
    let mut stage = LabelStage::default();
    for item in pending {
        let label = labels.get(&item.observation_id);
        match label {
            Some(label) => {
                apply_label_to_rooms(rooms, &item, &label.category, label.confidence);
                stage.labelled += 1;
            }
            None => stage.unresolved.push(item),
        }
    }
    Ok(stage)
}

fn apply_label_to_rooms(
    rooms: &mut [RoomState],
    item: &PendingObservation,
    category: &str,
    confidence: f64,
) {
    let observation = rooms
        .iter_mut()
        .find(|r| r.room_id == item.room_id)
        .and_then(|r| r.observations.get_mut(&item.observation_id));
    if let Some(observation) = observation {
        apply_label(observation, category, confidence);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn room_with(observations: Vec<Value>) -> RoomState {
        let mut room = RoomState::new("r1");
        for o in observations {
            room.observations
                .insert(o["id"].as_str().unwrap().to_string(), o);
        }
        room
    }

    #[test]
    fn only_uncategorised_observations_are_pending() {
        let room = room_with(vec![
            json!({"id": "a", "category": "toilet"}),
            json!({"id": "b", "crop_artifact_id": "00000000-0000-0000-0000-000000000001"}),
            json!({"id": "c", "category": ""}),
        ]);
        let pending = pending_observations(&[room]);
        let ids: Vec<_> = pending.iter().map(|p| p.observation_id.as_str()).collect();
        assert_eq!(ids, vec!["b", "c"]);
        assert!(pending[0].crop_artifact_id.is_some());
        assert!(pending[1].crop_artifact_id.is_none());
    }
}
