use serde::{Deserialize, Serialize};
use serde_json::Value;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::findings::{Finding, Summary};
use crate::scans::models::Report;

#[derive(Clone, Debug, Deserialize, ToSchema)]
pub struct RoomUpdate {
    pub room_id: String,
    #[serde(default, rename = "final")]
    pub finalized: bool,
    #[schema(value_type = Option<Object>)]
    pub captured_room: Option<Value>,
    #[serde(default)]
    #[schema(value_type = Vec<Object>)]
    pub observations: Vec<Value>,
    pub seq: Option<u64>,
}

#[derive(Clone, Debug, Deserialize, ToSchema)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ClientMessage {
    Room(RoomUpdate),
    Ping,
}

#[derive(Clone, Debug, Serialize, ToSchema)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ServerMessage {
    Hello {
        scan_id: Uuid,
        rooms: Vec<String>,
        findings: Vec<Finding>,
        summary: Summary,
    },
    Findings {
        room_id: String,
        seq: Option<u64>,
        #[serde(rename = "final")]
        finalized: bool,
        findings: Vec<Finding>,
        summary: Summary,
        elapsed_ms: u64,
    },
    Room {
        #[schema(value_type = Object)]
        room: Value,
    },
    Scene {
        #[schema(value_type = Object)]
        scene: Value,
    },
    Report {
        report: Box<Report>,
    },
    Error {
        message: String,
    },
    Pong,
}

impl ServerMessage {
    pub fn error(message: impl Into<String>) -> Self {
        Self::Error {
            message: message.into(),
        }
    }
}

pub fn validate_update(update: &RoomUpdate) -> Result<(), String> {
    if update.room_id.is_empty() || update.room_id.len() > 128 {
        return Err("room_id must be 1 to 128 characters".to_string());
    }
    let missing_id = update
        .observations
        .iter()
        .any(|o| o.get("id").and_then(Value::as_str).is_none());
    if missing_id {
        return Err("every observation needs a string id".to_string());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_room_message_with_final_flag() {
        let msg: ClientMessage = serde_json::from_str(
            r#"{"type":"room","room_id":"r1","final":true,"captured_room":{"doors":[]}}"#,
        )
        .unwrap();
        let ClientMessage::Room(update) = msg else {
            panic!("expected room message");
        };
        assert!(update.finalized);
        assert!(validate_update(&update).is_ok());
    }

    #[test]
    fn rejects_observation_without_id() {
        let update = RoomUpdate {
            room_id: "r1".into(),
            finalized: false,
            captured_room: None,
            observations: vec![serde_json::json!({"category": "toilet"})],
            seq: None,
        };
        assert!(validate_update(&update).is_err());
    }
}
