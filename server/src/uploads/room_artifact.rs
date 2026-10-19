use serde_json::Value;
use uuid::Uuid;

use super::models::UploadRecord;
use crate::engine::{assemble_scene, RoomInput};
use crate::error::{ApiError, ApiResult};
use crate::live::protocol::{validate_update, RoomUpdate};
use crate::live::rooms::{scan_accepts_updates, upsert_room};
use crate::state::AppState;

pub const ROOM_KIND: &str = "room";
const MAX_ROOM_BYTES: i64 = 16 * 1024 * 1024;

pub fn is_room(upload: &UploadRecord) -> bool {
    upload.kind == ROOM_KIND
}

pub async fn require_scan_capturing(state: &AppState, scan_id: Uuid) -> ApiResult<()> {
    let accepting = scan_accepts_updates(&state.db, scan_id).await?;
    if accepting {
        return Ok(());
    }
    Err(ApiError::Conflict(
        "scan is no longer accepting rooms".to_string(),
    ))
}

fn room_id_of(capture: &Value, filename: &str) -> String {
    let identifier = capture.get("identifier").and_then(Value::as_str);
    let stem = filename.rsplit_once('.').map_or(filename, |(stem, _)| stem);
    identifier.unwrap_or(stem).to_string()
}

fn update_from_capture(capture: Value, filename: &str) -> Result<RoomUpdate, String> {
    if !capture.is_object() {
        return Err("room upload must be a CapturedRoom JSON object".to_string());
    }
    let update = RoomUpdate {
        room_id: room_id_of(&capture, filename),
        finalized: true,
        captured_room: Some(capture),
        observations: Vec::new(),
        seq: None,
    };
    validate_update(&update)?;
    ensure_converts(&update)?;
    Ok(update)
}

fn ensure_converts(update: &RoomUpdate) -> Result<(), String> {
    let input = RoomInput {
        room_id: update.room_id.clone(),
        captured_room: update.captured_room.clone(),
        observations: Vec::new(),
    };
    assemble_scene(&[input])
        .map(|_| ())
        .map_err(|err| format!("room upload is not a valid CapturedRoom: {err:#}"))
}

/// Applies an uploaded CapturedRoom exactly as a live-socket room message would: it is
/// stored under its room id (so the same room arriving twice replaces, never duplicates)
/// and pushed to any open live session.
pub async fn apply_room_upload(state: &AppState, upload: &UploadRecord) -> ApiResult<()> {
    if upload.size_bytes > MAX_ROOM_BYTES {
        return Err(ApiError::Unprocessable("room upload is too large".into()));
    }
    let bytes = state
        .storage
        .get_bytes(&upload.s3_key)
        .await
        .map_err(|e| ApiError::Storage(format!("{e:#}")))?;
    let capture: Value = serde_json::from_slice(&bytes)
        .map_err(|e| ApiError::Unprocessable(format!("room upload is not JSON: {e}")))?;
    let update = update_from_capture(capture, &upload.filename).map_err(ApiError::Unprocessable)?;
    upsert_room(&state.db, upload.scan_id, &update).await?;
    publish_to_live_session(state, upload.scan_id, update).await;
    Ok(())
}

async fn publish_to_live_session(state: &AppState, scan_id: Uuid, update: RoomUpdate) {
    let Some(session) = state.hub.peek(scan_id).await else {
        return;
    };
    match session.apply_update(update).await {
        Ok(messages) => messages
            .into_iter()
            .for_each(|message| session.publish(message)),
        Err(err) => tracing::warn!(error = ?err, "uploaded room not pushed to live session"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn identifier_names_the_room_and_filename_is_the_fallback() {
        let with_id = json!({"identifier": "ROOM-A"});
        assert_eq!(room_id_of(&with_id, "x.json"), "ROOM-A");
        assert_eq!(room_id_of(&json!({}), "kitchen.room.json"), "kitchen.room");
    }

    #[test]
    fn non_objects_are_rejected() {
        assert!(update_from_capture(json!([1]), "a.json").is_err());
    }
}
