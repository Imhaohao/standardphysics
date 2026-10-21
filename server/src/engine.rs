//! The only module that touches `sp-core`. Everything else works with the server's own types.

use std::collections::BTreeMap;
use std::sync::OnceLock;

use anyhow::{anyhow, Context, Result};
use serde_json::{json, Value};
use sp_core::metrics::Catalog;
use sp_core::roomplan::{detect_connections, import_captured_json};
use sp_core::scene::{Object, ObjectSource, Observation, Room, Scene};
use sp_core::Engine;

use crate::findings::{EvaluationReport, Finding, Governing, StatusCounts};

const METRICS_JSON: &str = include_str!("../../rules/metrics.json");
const ADA_JSON: &str = include_str!("../../rules/ada2010.json");
const CBC_JSON: &str = include_str!("../../rules/cbc11b.json");

#[derive(Clone, Debug, Default)]
pub struct RoomInput {
    pub room_id: String,
    pub captured_room: Option<Value>,
    pub observations: Vec<Value>,
}

#[derive(Debug, Default)]
pub struct UpdatedRoom {
    pub room: Option<Value>,
    pub findings: Vec<Finding>,
}

fn build_room(input: &RoomInput, catalog: &Catalog) -> Result<Option<Room>> {
    let Some(capture) = &input.captured_room else {
        return Ok(None);
    };
    let mut room = room_from_capture(input, capture)?;
    add_detector_objects(&mut room, &input.observations, catalog);
    Ok(Some(room))
}

fn scene_from_inputs(inputs: &[RoomInput], catalog: &Catalog) -> Result<Scene> {
    let mut scene = Scene::default();
    for input in inputs {
        if let Some(room) = build_room(input, catalog)? {
            scene.upsert_room(room);
        }
    }
    scene.connections = detect_connections(&scene.rooms);
    scene.observations = inputs
        .iter()
        .flat_map(|i| i.observations.iter())
        .filter(|v| is_scene_observation(v))
        .filter_map(|v| serde_json::from_value(v.clone()).ok())
        .collect();
    Ok(scene)
}

/// The merged scene for a set of captured rooms, without evaluating any rule.
pub fn assemble_scene(inputs: &[RoomInput]) -> Result<Option<Value>> {
    let scene = scene_from_inputs(inputs, &Catalog::from_json(METRICS_JSON)?)?;
    if scene.rooms.is_empty() {
        return Ok(None);
    }
    Ok(Some(serde_json::to_value(scene)?))
}

pub struct SceneEngine {
    inner: Engine,
    scene_observations: BTreeMap<String, Observation>,
}

fn catalog() -> Option<&'static Catalog> {
    static CATALOG: OnceLock<Option<Catalog>> = OnceLock::new();
    CATALOG
        .get_or_init(|| Catalog::from_json(METRICS_JSON).ok())
        .as_ref()
}

pub fn object_categories() -> &'static [String] {
    static CATEGORIES: OnceLock<Vec<String>> = OnceLock::new();
    CATEGORIES.get_or_init(|| {
        catalog()
            .map(|c| c.object_categories.iter().map(|d| d.id.clone()).collect())
            .unwrap_or_default()
    })
}

/// The unit an answer to `metric` is recorded in, or `None` when the metric is not in the catalog.
pub fn answer_unit(metric: &str) -> Option<String> {
    catalog()?.metric(metric).map(|def| def.raw_unit.clone())
}

fn is_scene_observation(value: &Value) -> bool {
    value.get("metric").is_some()
}

fn is_detector_object(value: &Value) -> bool {
    value.get("category").is_some() && value.get("center").is_some() && value.get("size").is_some()
}

fn complete_object_json(value: &Value) -> Value {
    let mut object = value.clone();
    if object.get("yaw").is_none() {
        object["yaw"] = json!(0.0);
    }
    if object.get("top_height").is_none() {
        let center_y = object["center"]["y"].as_f64().unwrap_or(0.0);
        let height = object["size"]["y"].as_f64().unwrap_or(0.0);
        object["top_height"] = json!(center_y + height / 2.0);
    }
    object["source"] = json!("detector");
    object
}

fn detector_object(value: &Value) -> Result<Object> {
    let object: Object = serde_json::from_value(complete_object_json(value))
        .context("detector observation is not a valid object")?;
    debug_assert_eq!(object.source, ObjectSource::Detector);
    Ok(object)
}

fn room_from_capture(input: &RoomInput, capture: &Value) -> Result<Room> {
    let rooms = import_captured_json(&capture.to_string())?;
    let mut room = rooms
        .into_iter()
        .next()
        .ok_or_else(|| anyhow!("capture contains no rooms"))?;
    room.id = input.room_id.clone();
    Ok(room)
}

fn add_detector_objects(room: &mut Room, observations: &[Value], catalog: &Catalog) {
    for value in observations.iter().filter(|v| is_detector_object(v)) {
        match detector_object(value) {
            Ok(object) if catalog.is_known_category(&object.category) => {
                room.objects.retain(|o| o.id != object.id);
                room.objects.push(object);
            }
            Ok(object) => {
                tracing::warn!(category = %object.category, "unknown object category ignored")
            }
            Err(err) => tracing::warn!(error = %err, "detector observation ignored"),
        }
    }
}

impl SceneEngine {
    pub fn new() -> Result<Self> {
        Ok(Self {
            inner: Engine::new(METRICS_JSON, &[ADA_JSON, CBC_JSON])?,
            scene_observations: BTreeMap::new(),
        })
    }

    fn remember_scene_observations(&mut self, observations: &[Value]) {
        for value in observations.iter().filter(|v| is_scene_observation(v)) {
            match serde_json::from_value::<Observation>(value.clone()) {
                Ok(observation) => {
                    self.scene_observations
                        .insert(observation.id.clone(), observation);
                }
                Err(err) => tracing::warn!(error = %err, "scene observation ignored"),
            }
        }
    }

    pub fn update_room(&mut self, input: RoomInput) -> Result<UpdatedRoom> {
        self.remember_scene_observations(&input.observations);
        let Some(room) = build_room(&input, self.inner.catalog())? else {
            return Ok(UpdatedRoom::default());
        };
        let room_json = serde_json::to_value(&room)?;
        let touched = self.inner.update_room(room);
        Ok(UpdatedRoom {
            room: Some(room_json),
            findings: touched.iter().map(Finding::from_core).collect(),
        })
    }

    /// Replace the whole scene without evaluating; follow with `evaluate_all`.
    pub fn load_rooms(&mut self, inputs: &[RoomInput]) -> Result<()> {
        let scene = scene_from_inputs(inputs, self.inner.catalog())?;
        self.inner.set_scene(scene);
        Ok(())
    }

    pub fn scene_json(&self) -> Result<Option<Value>> {
        let scene = self.inner.scene();
        if scene.rooms.is_empty() {
            return Ok(None);
        }
        Ok(Some(serde_json::to_value(scene)?))
    }

    pub fn all_findings(&self) -> Vec<Finding> {
        self.inner
            .findings()
            .iter()
            .map(Finding::from_core)
            .collect()
    }

    pub fn evaluate_all(&mut self) -> Result<EvaluationReport> {
        let mut scene = self.inner.scene().clone();
        scene
            .observations
            .extend(self.scene_observations.values().cloned());
        self.inner.set_scene(scene);
        let report = self.inner.evaluate_all();
        Ok(EvaluationReport {
            findings: self.all_findings(),
            governing_counts: StatusCounts {
                pass: report.governing_counts.pass as u32,
                fail: report.governing_counts.fail as u32,
                needs_info: report.governing_counts.needs_info as u32,
                not_applicable: report.governing_counts.not_applicable as u32,
            },
            governing: report.governing.iter().map(Governing::from_core).collect(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const ROOM_JSON: &str = include_str!("../../datasets/phone/test1/room.json");

    /// Exactly what the iOS app sends for a detector object (`DetectedObject` encoded as JSON).
    fn phone_detector_observation() -> Value {
        json!({
            "id": "detector-fridge", "category": "refrigerator", "label": "refrigerator",
            "center": {"x": -4.9, "y": 0.85, "z": -1.0}, "size": {"x": 0.7, "y": 1.7, "z": 0.7},
            "yaw": 0.0, "top_height": 1.7, "confidence": 0.8, "hits": 4
        })
    }

    #[test]
    fn phone_detector_observations_become_detector_objects() {
        let mut engine = SceneEngine::new().unwrap();
        let updated = engine
            .update_room(RoomInput {
                room_id: "0".into(),
                captured_room: Some(serde_json::from_str(ROOM_JSON).unwrap()),
                observations: vec![phone_detector_observation()],
            })
            .unwrap();
        let room = updated.room.unwrap();
        let objects = room["objects"].as_array().unwrap();
        let fridge = objects
            .iter()
            .find(|o| o["id"] == "detector-fridge")
            .unwrap();
        assert_eq!(fridge["source"], "detector");
        assert_eq!(fridge["category"], "refrigerator");
        assert_eq!(fridge["top_height"], 1.7);
        assert_eq!(objects.len(), 17);
    }
}
