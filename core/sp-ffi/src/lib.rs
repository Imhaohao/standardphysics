//! UniFFI (proc-macro) bindings for Swift. Build the XCFramework with `core/scripts/build-xcframework.sh`.

mod records;

pub use records::*;
use sp_core::Engine;
use sp_core::roomplan::{detect_connections, import_captured_json, merge_rooms};
use sp_core::scene::Scene;
use std::sync::{Arc, Mutex, MutexGuard};

uniffi::setup_scaffolding!();

#[derive(Debug, thiserror::Error, uniffi::Error)]
pub enum SpError {
    #[error("invalid input: {message}")]
    InvalidInput { message: String },
    #[error("engine error: {message}")]
    Engine { message: String },
}

fn invalid(error: impl std::fmt::Display) -> SpError {
    SpError::InvalidInput { message: error.to_string() }
}

/// Import a RoomPlan `CapturedRoom` or `CapturedStructure` JSON into rooms (floor at y = 0).
#[uniffi::export]
pub fn import_roomplan(json: String) -> Result<Vec<SpRoom>, SpError> {
    let rooms = import_captured_json(&json).map_err(invalid)?;
    Ok(rooms.into_iter().map(Into::into).collect())
}

/// Import and merge RoomPlan captures into a Scene, returned as Scene JSON (`core/schema/scene.schema.json`).
#[uniffi::export]
pub fn roomplan_to_scene_json(captures: Vec<String>) -> Result<String, SpError> {
    let mut rooms = Vec::new();
    for json in &captures {
        rooms.extend(import_captured_json(json).map_err(invalid)?);
    }
    Ok(merge_rooms(rooms).to_json())
}

/// Version of the Scene contract this engine reads and writes.
#[uniffi::export]
pub fn scene_version() -> u32 {
    sp_core::scene::SCENE_VERSION
}

#[derive(uniffi::Object)]
pub struct SpEngine {
    engine: Mutex<Engine>,
}

#[uniffi::export]
impl SpEngine {
    /// Load the metric catalog (`rules/metrics.json`) and rulepacks (`rules/ada2010.json`, `rules/cbc11b.json`).
    #[uniffi::constructor]
    pub fn new(catalog_json: String, rulepack_jsons: Vec<String>) -> Result<Arc<Self>, SpError> {
        let packs: Vec<&str> = rulepack_jsons.iter().map(String::as_str).collect();
        let engine = Engine::new(&catalog_json, &packs).map_err(|e| SpError::Engine { message: e.to_string() })?;
        Ok(Arc::new(Self { engine: Mutex::new(engine) }))
    }

    /// Replace the scene with Scene JSON.
    pub fn set_scene_json(&self, scene_json: String) -> Result<(), SpError> {
        let scene = Scene::from_json(&scene_json).map_err(invalid)?;
        self.lock().set_scene(scene);
        Ok(())
    }

    pub fn scene_json(&self) -> String {
        self.lock().scene().to_json()
    }

    /// Add or replace a room and re-evaluate only its storey; returns the affected findings.
    pub fn update_room(&self, room: SpRoom) -> Vec<SpFinding> {
        self.lock().update_room(room.into()).into_iter().map(Into::into).collect()
    }

    /// Import one RoomPlan `CapturedRoom` JSON (live scanning) and update the engine with it.
    pub fn update_roomplan_room(&self, captured_room_json: String) -> Result<Vec<SpFinding>, SpError> {
        let rooms = import_captured_json(&captured_room_json).map_err(invalid)?;
        let mut engine = self.lock();
        let findings = rooms.into_iter().flat_map(|room| engine.update_room(room)).collect::<Vec<_>>();
        Ok(findings.into_iter().map(Into::into).collect())
    }

    /// Add owner answers, photo labels or tape measurements. Takes effect at the next evaluation.
    pub fn add_observations(&self, observations: Vec<SpObservation>) {
        let mut engine = self.lock();
        let mut scene = engine.scene().clone();
        scene.observations.extend(observations.into_iter().map(Into::into));
        scene.connections = detect_connections(&scene.rooms);
        engine.set_scene(scene);
    }

    pub fn evaluate_all(&self) -> SpReport {
        self.lock().evaluate_all().into()
    }

    pub fn findings(&self) -> Vec<SpFinding> {
        self.lock().findings().into_iter().map(Into::into).collect()
    }

    /// The current report as JSON (for upload to the server).
    pub fn report_json(&self) -> String {
        serde_json::to_string(&self.lock().report()).unwrap_or_default()
    }
}

impl SpEngine {
    fn lock(&self) -> MutexGuard<'_, Engine> {
        self.engine.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn read(path: &str) -> String {
        std::fs::read_to_string(format!("{}/../../{path}", env!("CARGO_MANIFEST_DIR"))).unwrap()
    }

    #[test]
    fn imports_apple_sample_through_the_binding() {
        let rooms = import_roomplan(read("packages/fixtures/standardphysics_fixtures/data/real/apple_bedroom3.room.json")).unwrap();
        assert_eq!(rooms.len(), 1);
        assert_eq!(rooms[0].openings.iter().filter(|o| o.kind == SpOpeningKind::Door).count(), 2);
    }

    #[test]
    fn engine_round_trip() {
        let Ok(catalog) = std::fs::read_to_string(format!("{}/../../rules/metrics.json", env!("CARGO_MANIFEST_DIR"))) else { return };
        let packs = vec![read("rules/ada2010.json"), read("rules/cbc11b.json")];
        let engine = SpEngine::new(catalog, packs).unwrap();
        let rooms = import_roomplan(read("packages/fixtures/standardphysics_fixtures/data/real/apple_livingroom.room.json")).unwrap();
        let findings = engine.update_room(rooms[0].clone());
        assert!(!findings.is_empty());
        let report = engine.evaluate_all();
        assert_eq!(report.jurisdictions.len(), 2);
        assert!(engine.report_json().contains("governing"));
    }
}
