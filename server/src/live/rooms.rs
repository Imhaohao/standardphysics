use std::collections::BTreeMap;

use anyhow::Result;
use serde_json::Value;
use sqlx::types::Json;
use sqlx::PgPool;
use uuid::Uuid;

use super::protocol::RoomUpdate;
use crate::engine::RoomInput;

#[derive(Clone, Debug, Default)]
pub struct RoomState {
    pub room_id: String,
    pub captured_room: Option<Value>,
    pub observations: BTreeMap<String, Value>,
    pub finalized: bool,
}

pub fn observation_id(observation: &Value) -> Option<String> {
    observation.get("id")?.as_str().map(str::to_string)
}

impl RoomState {
    pub fn new(room_id: &str) -> Self {
        Self {
            room_id: room_id.to_string(),
            ..Self::default()
        }
    }

    pub fn apply(&mut self, update: &RoomUpdate) {
        if let Some(room) = &update.captured_room {
            self.captured_room = Some(room.clone());
        }
        for observation in &update.observations {
            if let Some(id) = observation_id(observation) {
                self.observations.insert(id, observation.clone());
            }
        }
        self.finalized |= update.finalized;
    }

    pub fn to_input(&self) -> RoomInput {
        RoomInput {
            room_id: self.room_id.clone(),
            captured_room: self.captured_room.clone(),
            observations: self.observations.values().cloned().collect(),
        }
    }
}

fn observations_object(update: &RoomUpdate) -> Value {
    let map: serde_json::Map<String, Value> = update
        .observations
        .iter()
        .filter_map(|o| Some((observation_id(o)?, o.clone())))
        .collect();
    Value::Object(map)
}

pub async fn scan_accepts_updates(db: &PgPool, scan_id: Uuid) -> Result<bool> {
    let status: Option<(String,)> = sqlx::query_as("SELECT status FROM scans WHERE id = $1")
        .bind(scan_id)
        .fetch_optional(db)
        .await?;
    Ok(status.is_some_and(|(s,)| s == "capturing"))
}

pub async fn upsert_room(db: &PgPool, scan_id: Uuid, update: &RoomUpdate) -> Result<()> {
    sqlx::query(
        "INSERT INTO scan_rooms (scan_id, room_id, captured_room, observations, finalized)
         VALUES ($1, $2, $3, $4, $5)
         ON CONFLICT (scan_id, room_id) DO UPDATE SET
            captured_room = COALESCE(EXCLUDED.captured_room, scan_rooms.captured_room),
            observations = scan_rooms.observations || EXCLUDED.observations,
            finalized = scan_rooms.finalized OR EXCLUDED.finalized,
            updated_at = now()",
    )
    .bind(scan_id)
    .bind(&update.room_id)
    .bind(update.captured_room.as_ref().map(Json))
    .bind(Json(observations_object(update)))
    .bind(update.finalized)
    .execute(db)
    .await?;
    Ok(())
}

type RoomRow = (
    String,
    Option<Json<Value>>,
    Json<BTreeMap<String, Value>>,
    bool,
);

pub async fn load_rooms(db: &PgPool, scan_id: Uuid) -> Result<Vec<RoomState>> {
    let rows: Vec<RoomRow> = sqlx::query_as(
        "SELECT room_id, captured_room, observations, finalized FROM scan_rooms
         WHERE scan_id = $1 ORDER BY room_id",
    )
    .bind(scan_id)
    .fetch_all(db)
    .await?;
    Ok(rows
        .into_iter()
        .map(|(room_id, room, observations, finalized)| RoomState {
            room_id,
            captured_room: room.map(|j| j.0),
            observations: observations.0,
            finalized,
        })
        .collect())
}
