use std::collections::HashMap;

use anyhow::Result;
use serde_json::{json, Value};
use sqlx::PgPool;
use uuid::Uuid;

use crate::engine::object_categories;
use crate::live::rooms::RoomState;
use crate::state::AppState;
use crate::vision::{group_by_id, LabelQuestion, LabelRequest, LabelResult};
use crate::vision_cache::{self, cache_key};

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

pub(crate) fn crop_artifact_id(observation: &Value) -> Option<Uuid> {
    observation.get("crop_artifact_id")?.as_str()?.parse().ok()
}

/// A request to check a RoomPlan object's category; `finish::relabel` handles it.
pub fn is_relabel(observation: &Value) -> bool {
    observation.get("relabel_object_id").is_some()
}

fn needs_label(observation: &Value) -> bool {
    !has_category(observation) && observation.get("metric").is_none() && !is_relabel(observation)
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

pub(crate) struct CropLocation {
    pub key: String,
    pub content_type: String,
    pub sha256: String,
}

/// Where this scan's crops are stored; ids that belong to another scan are left out.
pub(crate) async fn crop_locations(
    db: &PgPool,
    scan_id: Uuid,
    ids: Vec<Uuid>,
) -> Result<HashMap<Uuid, CropLocation>> {
    if ids.is_empty() {
        return Ok(HashMap::new());
    }
    let rows: Vec<(Uuid, String, String, String)> = sqlx::query_as(
        "SELECT id, s3_key, content_type, sha256 FROM artifacts WHERE scan_id = $1 AND id = ANY($2)",
    )
    .bind(scan_id)
    .bind(&ids)
    .fetch_all(db)
    .await?;
    Ok(rows
        .into_iter()
        .map(|(id, key, content_type, sha256)| {
            (
                id,
                CropLocation {
                    key,
                    content_type,
                    sha256,
                },
            )
        })
        .collect())
}

fn label_requests(
    pending: &[PendingObservation],
    locations: &HashMap<Uuid, CropLocation>,
) -> Vec<LabelRequest> {
    pending
        .iter()
        .filter_map(|p| {
            let crop = locations.get(&p.crop_artifact_id?)?;
            Some(LabelRequest {
                observation_id: p.observation_id.clone(),
                crop_key: crop.key.clone(),
                content_type: crop.content_type.clone(),
                image_sha256: crop.sha256.clone(),
                context: String::new(),
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
    let crop_ids = pending.iter().filter_map(|p| p.crop_artifact_id).collect();
    let locations = crop_locations(&state.db, scan_id, crop_ids).await?;
    let requests = label_requests(&pending, &locations);
    let categories = object_categories();
    let labels =
        label_with_cache(state, scan_id, LabelQuestion::Object, categories, requests).await?;
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

/// Bump when the relabel prompt changes, so old replies are not reused for a new question.
const RELABEL_PROMPT_VERSION: &str = "relabel-v1";

fn label_cache_key(
    question: LabelQuestion,
    model: &str,
    categories: &[String],
    request: &LabelRequest,
) -> String {
    let categories = categories.join(",");
    match question {
        LabelQuestion::Object => cache_key(&["label", model, &categories, &request.image_sha256]),
        LabelQuestion::Relabel => cache_key(&[
            RELABEL_PROMPT_VERSION,
            model,
            &categories,
            &request.context,
            &request.image_sha256,
        ]),
    }
}

fn cached_label(reply: &Value, observation_id: &str) -> Option<LabelResult> {
    Some(LabelResult {
        observation_id: observation_id.to_string(),
        category: reply.get("category")?.as_str()?.to_string(),
        confidence: reply.get("confidence")?.as_f64()?,
        built_in: reply.get("built_in").and_then(Value::as_bool),
    })
}

fn cache_entry(label: &LabelResult) -> Value {
    let mut entry = json!({"category": label.category, "confidence": label.confidence});
    if let Some(built_in) = label.built_in {
        entry["built_in"] = json!(built_in);
    }
    entry
}

/// Labels from the cache first; only crops never seen before go to the model.
pub(crate) async fn label_with_cache(
    state: &AppState,
    scan_id: Uuid,
    question: LabelQuestion,
    categories: &[String],
    requests: Vec<LabelRequest>,
) -> Result<HashMap<String, LabelResult>> {
    let model = state.labeller.model().to_string();
    let key_of = |r: &LabelRequest| label_cache_key(question, &model, categories, r);
    let keys: Vec<String> = requests.iter().map(key_of).collect();
    let cached = vision_cache::lookup(&state.db, &keys).await?;
    let (hits, misses): (Vec<_>, Vec<_>) = requests
        .into_iter()
        .partition(|r| cached.contains_key(&key_of(r)));
    let mut results: Vec<LabelResult> = hits
        .iter()
        .filter_map(|r| cached_label(&cached[&key_of(r)], &r.observation_id))
        .collect();
    let keys_by_id: HashMap<String, String> = misses
        .iter()
        .map(|r| (r.observation_id.clone(), key_of(r)))
        .collect();
    let outcome = state
        .labeller
        .label_all(&state.storage, question, categories, misses)
        .await;
    if outcome.deadline_hit {
        tracing::warn!(%scan_id, ?question, missing = outcome.unlabelled.len(), "vision labelling hit its deadline");
    }
    let fresh: Vec<(String, Value)> = outcome
        .labelled
        .iter()
        .filter_map(|l| Some((keys_by_id.get(&l.observation_id)?.clone(), cache_entry(l))))
        .collect();
    vision_cache::store(&state.db, &fresh).await?;
    results.extend(outcome.labelled);
    Ok(group_by_id(results))
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
            json!({"id": "relabel-x", "relabel_object_id": "X"}),
        ]);
        let pending = pending_observations(&[room]);
        let ids: Vec<_> = pending.iter().map(|p| p.observation_id.as_str()).collect();
        assert_eq!(ids, vec!["b", "c"]);
        assert!(pending[0].crop_artifact_id.is_some());
        assert!(pending[1].crop_artifact_id.is_none());
    }
}
