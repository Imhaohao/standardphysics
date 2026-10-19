mod common;

use std::time::Instant;

use common::{connect_live, door_room, next_of_type, send_json, TestApp};
use serde_json::json;

fn room_message(room_id: &str, door_width: f64, is_final: bool) -> serde_json::Value {
    json!({
        "type": "room", "room_id": room_id, "final": is_final, "seq": 1,
        "captured_room": door_room(room_id, door_width),
        "observations": [{"id": format!("{room_id}-obs"), "category": "toilet"}],
    })
}

#[tokio::test]
async fn phone_room_update_returns_findings_to_phone_and_viewer() {
    let app = TestApp::start().await;
    let token = app.register("live@example.com").await;
    let scan_id = app.create_scan(&token).await;

    let mut phone = connect_live(&app, &token, &scan_id, "writer").await;
    let hello = next_of_type(&mut phone, "hello").await;
    assert_eq!(hello["scan_id"], scan_id);
    assert!(hello["findings"].as_array().unwrap().is_empty());

    let mut viewer = connect_live(&app, &token, &scan_id, "viewer").await;
    next_of_type(&mut viewer, "hello").await;

    let sent_at = Instant::now();
    send_json(&mut phone, room_message("r1", 0.70, false)).await;
    let on_phone = next_of_type(&mut phone, "findings").await;
    let round_trip = sent_at.elapsed();
    assert!(
        round_trip.as_millis() < 1000,
        "round trip took {round_trip:?}"
    );
    assert_eq!(on_phone["room_id"], "r1");
    assert_eq!(on_phone["seq"], 1);
    assert_eq!(on_phone["findings"][0]["status"], "fail");
    assert_eq!(on_phone["summary"]["total"]["fail"], 1);

    let on_viewer = next_of_type(&mut viewer, "findings").await;
    assert_eq!(on_viewer["findings"], on_phone["findings"]);

    send_json(&mut phone, room_message("r2", 0.95, true)).await;
    let second = next_of_type(&mut viewer, "findings").await;
    assert_eq!(second["findings"][0]["status"], "pass");
    assert_eq!(second["summary"]["total"]["pass"], 1);
    assert_eq!(second["summary"]["total"]["fail"], 1);
}

#[tokio::test]
async fn viewer_is_read_only_and_bad_messages_get_errors() {
    let app = TestApp::start().await;
    let token = app.register("ro@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let mut viewer = connect_live(&app, &token, &scan_id, "viewer").await;
    next_of_type(&mut viewer, "hello").await;

    send_json(&mut viewer, room_message("r1", 0.7, false)).await;
    let error = next_of_type(&mut viewer, "error").await;
    assert!(error["message"].as_str().unwrap().contains("read-only"));

    send_json(&mut viewer, json!({"type": "nonsense"})).await;
    next_of_type(&mut viewer, "error").await;
    send_json(&mut viewer, json!({"type": "ping"})).await;
    next_of_type(&mut viewer, "pong").await;

    let mut phone = connect_live(&app, &token, &scan_id, "writer").await;
    next_of_type(&mut phone, "hello").await;
    send_json(
        &mut phone,
        json!({"type": "room", "room_id": "", "captured_room": {}}),
    )
    .await;
    next_of_type(&mut phone, "error").await;
    send_json(
        &mut phone,
        json!({"type": "room", "room_id": "r", "observations": [{"category": "x"}]}),
    )
    .await;
    next_of_type(&mut phone, "error").await;

    let rooms: i64 = sqlx::query_scalar("SELECT count(*) FROM scan_rooms")
        .fetch_one(&app.db)
        .await
        .unwrap();
    assert_eq!(rooms, 0);
}

#[tokio::test]
async fn reconnect_restores_state_from_the_database() {
    let app = TestApp::start().await;
    let token = app.register("resume@example.com").await;
    let scan_id = app.create_scan(&token).await;

    let mut phone = connect_live(&app, &token, &scan_id, "writer").await;
    next_of_type(&mut phone, "hello").await;
    send_json(&mut phone, room_message("r1", 0.7, false)).await;
    next_of_type(&mut phone, "findings").await;
    send_json(&mut phone, json!({"type": "room", "room_id": "r1", "observations": [{"id": "late", "category": "sink"}]})).await;
    next_of_type(&mut phone, "findings").await;
    drop(phone);
    common::wait_until("session eviction", || async {
        app.state.hub.peek(scan_id.parse().unwrap()).await.is_none()
    })
    .await;

    let mut resumed = connect_live(&app, &token, &scan_id, "writer").await;
    let hello = next_of_type(&mut resumed, "hello").await;
    assert_eq!(hello["rooms"], json!(["r1"]));
    assert_eq!(hello["findings"][0]["status"], "fail");

    let observations: serde_json::Value =
        sqlx::query_scalar("SELECT observations FROM scan_rooms WHERE room_id = 'r1'")
            .fetch_one(&app.db)
            .await
            .unwrap();
    assert_eq!(
        observations.as_object().unwrap().len(),
        2,
        "partial updates merge instead of replacing"
    );
}
