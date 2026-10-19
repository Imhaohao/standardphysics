use std::collections::BTreeMap;

use anyhow::Result;
use serde_json::Value;

use crate::findings::{Finding, FindingStatus, Measured};

const MIN_DOOR_CLEAR_WIDTH_M: f64 = 0.815;

pub const DEFAULT_OBJECT_CATEGORIES: &[&str] = &[
    "toilet",
    "sink",
    "grab_bar",
    "door_hardware",
    "counter",
    "table",
    "sign",
    "ramp",
    "stairs",
    "other",
];

#[derive(Clone, Debug, Default)]
pub struct RoomInput {
    pub room_id: String,
    pub captured_room: Option<Value>,
    pub observations: Vec<Value>,
}

#[derive(Default)]
pub struct SceneEngine {
    rooms: BTreeMap<String, RoomInput>,
}

impl SceneEngine {
    pub fn new() -> Result<Self> {
        Ok(Self::default())
    }

    pub fn object_categories() -> Vec<String> {
        DEFAULT_OBJECT_CATEGORIES
            .iter()
            .map(|c| c.to_string())
            .collect()
    }

    pub fn update_room(&mut self, input: RoomInput) -> Result<Vec<Finding>> {
        let findings = evaluate_room(&input);
        self.rooms.insert(input.room_id.clone(), input);
        Ok(findings)
    }

    pub fn evaluate_all(&mut self) -> Result<Vec<Finding>> {
        Ok(self.rooms.values().flat_map(evaluate_room).collect())
    }
}

fn evaluate_room(input: &RoomInput) -> Vec<Finding> {
    let Some(room) = &input.captured_room else {
        return Vec::new();
    };
    let doors = room.get("doors").and_then(Value::as_array);
    doors
        .into_iter()
        .flatten()
        .filter_map(door_finding)
        .collect()
}

fn door_finding(door: &Value) -> Option<Finding> {
    let id = door.get("identifier")?.as_str()?.to_string();
    let width = door.get("dimensions")?.get(0)?.as_f64()?;
    let status = if width >= MIN_DOOR_CLEAR_WIDTH_M {
        FindingStatus::Pass
    } else {
        FindingStatus::Fail
    };
    Some(Finding {
        rule_id: "ADA2010-404.2.3".to_string(),
        jurisdiction: "ADA2010".to_string(),
        section: "404.2.3".to_string(),
        subject_id: id,
        status,
        measured: Some(Measured {
            value: width,
            unit: "m".to_string(),
        }),
        required: Some(
            serde_json::json!({"op": ">=", "value": MIN_DOOR_CLEAR_WIDTH_M, "unit": "m"}),
        ),
        message: "Door clear width".to_string(),
        evidence: None,
    })
}
