mod common;

use std::sync::atomic::Ordering;
use std::time::Instant;

use common::{
    connect_live, door_id, door_room_at, findings_for, next_of_type, send_json, upload_artifact,
    TestApp, TestOptions,
};
use reqwest::StatusCode;
use serde_json::{json, Value};

async fn send_room(
    app: &TestApp,
    token: &str,
    scan_id: &str,
    room: Value,
    observations: Vec<Value>,
) {
    let mut phone = connect_live(app, token, scan_id, "writer").await;
    next_of_type(&mut phone, "hello").await;
    let message = json!({
        "type": "room", "room_id": room["identifier"], "final": true,
        "captured_room": room, "observations": observations,
    });
    send_json(&mut phone, message).await;
    next_of_type(&mut phone, "findings").await;
}

async fn finish(app: &TestApp, token: &str, scan_id: &str) -> Value {
    let (status, report) = app
        .post(token, &format!("/v1/scans/{scan_id}/finish"), json!({}))
        .await;
    assert_eq!(status, StatusCode::OK, "{report}");
    report
}

#[tokio::test]
async fn finish_stores_the_assessment_and_pushes_the_report() {
    let app = TestApp::start().await;
    let token = app.register("finish@example.com").await;
    let scan_id = app.create_scan(&token).await;
    send_room(&app, &token, &scan_id, door_room_at("r1", 0.7, 1), vec![]).await;
    send_room(&app, &token, &scan_id, door_room_at("r2", 0.95, 2), vec![]).await;

    let mut viewer = connect_live(&app, &token, &scan_id, "viewer").await;
    next_of_type(&mut viewer, "hello").await;

    let (status, scene) = app.get(&token, &format!("/v1/scans/{scan_id}/scene")).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(scene["rooms"].as_array().unwrap().len(), 2);
    assert_eq!(scene["rooms"][0]["walls"].as_array().unwrap().len(), 4);

    let report = finish(&app, &token, &scan_id).await;
    let status_of = |room: &str| {
        let door = door_id(room);
        let found = findings_for(&report["findings"], &door);
        found
            .iter()
            .find(|f| f["rule_id"] == "ADA-404.2.3-clear-width")
            .map(|f| f["status"].clone())
            .unwrap()
    };
    assert_eq!(status_of("r1"), "fail");
    assert_eq!(status_of("r2"), "pass");
    assert!(
        report["summary"]["governing_counts"]["fail"]
            .as_u64()
            .unwrap()
            >= 1
    );
    assert!(!report["summary"]["governing"]
        .as_array()
        .unwrap()
        .is_empty());
    assert!(report["timings"]["total_ms"].is_u64());

    let pushed_scene = next_of_type(&mut viewer, "scene").await;
    assert_eq!(pushed_scene["scene"]["rooms"].as_array().unwrap().len(), 2);
    let pushed = next_of_type(&mut viewer, "report").await;
    assert_eq!(pushed["report"]["assessment_id"], report["assessment_id"]);

    let (status, stored) = app
        .get(&token, &format!("/v1/scans/{scan_id}/assessment"))
        .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(stored["findings"], report["findings"]);
    let (_, scan) = app.get(&token, &format!("/v1/scans/{scan_id}")).await;
    assert_eq!(scan["status"], "complete");

    let queued: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM jobs WHERE kind = 'texture_bake' AND state = 'queued'",
    )
    .fetch_one(&app.db)
    .await
    .unwrap();
    assert_eq!(queued, 1);

    let mut late = connect_live(&app, &token, &scan_id, "writer").await;
    next_of_type(&mut late, "hello").await;
    send_json(
        &mut late,
        json!({"type": "room", "room_id": "r3", "captured_room": door_room_at("r3", 1.0, 3)}),
    )
    .await;
    let error = next_of_type(&mut late, "error").await;
    assert!(error["message"]
        .as_str()
        .unwrap()
        .contains("no longer accepting"));
}

#[tokio::test]
async fn finish_labels_crops_concurrently_within_the_limit() {
    let app = TestApp::start_with(TestOptions {
        label_concurrency: 2,
        ..TestOptions::default()
    })
    .await;
    app.label_api.delay_ms.store(150, Ordering::SeqCst);
    let token = app.register("label@example.com").await;
    let scan_id = app.create_scan(&token).await;

    let mut observations = Vec::new();
    for i in 0..6 {
        let crop = upload_artifact(
            &app,
            &token,
            &scan_id,
            "crop",
            format!("jpeg-bytes-{i}").as_bytes(),
        )
        .await;
        observations.push(json!({"id": format!("o{i}"), "crop_artifact_id": crop}));
    }
    send_room(
        &app,
        &token,
        &scan_id,
        door_room_at("r1", 0.9, 1),
        observations,
    )
    .await;

    let report = finish(&app, &token, &scan_id).await;
    assert_eq!(report["labelled_by_vision"], 6);
    assert_eq!(report["unlabelled_objects"], 0);
    assert_eq!(app.label_api.calls.load(Ordering::SeqCst), 6);
    let peak = app.label_api.max_in_flight.load(Ordering::SeqCst);
    assert_eq!(
        peak, 2,
        "parallelism is bounded by LABEL_CONCURRENCY and actually used"
    );
    assert!(report["findings"]
        .as_array()
        .unwrap()
        .iter()
        .all(|f| f["rule_id"] != "label.unresolved"));
}

#[tokio::test]
async fn labelling_deadline_turns_dependent_findings_into_needs_info() {
    let app = TestApp::start_with(TestOptions {
        label_deadline_ms: 300,
        ..TestOptions::default()
    })
    .await;
    app.label_api.delay_ms.store(5_000, Ordering::SeqCst);
    let token = app.register("slow@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let crop = upload_artifact(&app, &token, &scan_id, "crop", b"jpeg").await;
    let observations = vec![
        json!({"id": "o1", "crop_artifact_id": crop}),
        json!({"id": "o2"}),
    ];
    send_room(
        &app,
        &token,
        &scan_id,
        door_room_at("r1", 0.9, 1),
        observations,
    )
    .await;

    let started = Instant::now();
    let report = finish(&app, &token, &scan_id).await;
    assert!(
        started.elapsed().as_millis() < 2_000,
        "finish must not wait for the slow labeller"
    );
    assert_eq!(report["unlabelled_objects"], 2);
    let unresolved: Vec<&Value> = report["findings"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|f| f["rule_id"] == "label.unresolved")
        .collect();
    assert_eq!(unresolved.len(), 2);
    assert!(unresolved.iter().all(|f| f["status"] == "needs_info"));
}

#[tokio::test]
async fn without_a_label_key_objects_stay_unresolved() {
    let app = TestApp::start_with(TestOptions {
        label_key: None,
        ..TestOptions::default()
    })
    .await;
    let token = app.register("nokey@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let crop = upload_artifact(&app, &token, &scan_id, "crop", b"jpeg").await;
    send_room(
        &app,
        &token,
        &scan_id,
        door_room_at("r1", 0.9, 1),
        vec![json!({"id": "o1", "crop_artifact_id": crop})],
    )
    .await;
    let report = finish(&app, &token, &scan_id).await;
    assert_eq!(report["unlabelled_objects"], 1);
    assert_eq!(app.label_api.calls.load(Ordering::SeqCst), 0);
}

#[tokio::test]
async fn crop_ids_from_other_scans_are_not_followed() {
    let app = TestApp::start().await;
    let token = app.register("cross@example.com").await;
    let other_scan = app.create_scan(&token).await;
    let foreign_crop = upload_artifact(&app, &token, &other_scan, "crop", b"jpeg").await;
    let scan_id = app.create_scan(&token).await;
    send_room(
        &app,
        &token,
        &scan_id,
        door_room_at("r1", 0.9, 1),
        vec![json!({"id": "o1", "crop_artifact_id": foreign_crop})],
    )
    .await;
    let report = finish(&app, &token, &scan_id).await;
    assert_eq!(report["unlabelled_objects"], 1);
    assert_eq!(app.label_api.calls.load(Ordering::SeqCst), 0);
}

#[tokio::test]
async fn ten_room_scan_finishes_far_inside_the_budget() {
    let app = TestApp::start().await;
    let token = app.register("budget@example.com").await;
    let scan_id = app.create_scan(&token).await;
    for i in 0..10 {
        let width = if i % 3 == 0 { 0.7 } else { 0.95 };
        send_room(
            &app,
            &token,
            &scan_id,
            door_room_at(&format!("room-{i}"), width, i),
            vec![],
        )
        .await;
    }
    let started = Instant::now();
    let report = finish(&app, &token, &scan_id).await;
    let wall = started.elapsed();
    println!("FINISH_TIMING wall={wall:?} stages={}", report["timings"]);
    assert!(wall.as_secs() < 60);
    assert!(report["findings"].as_array().unwrap().len() > 10 * 50);
}

#[tokio::test]
async fn concurrent_finish_is_rejected() {
    let app = TestApp::start().await;
    let token = app.register("twice@example.com").await;
    let scan_id = app.create_scan(&token).await;
    sqlx::query("UPDATE scans SET status = 'finishing'")
        .execute(&app.db)
        .await
        .unwrap();
    let (status, _) = app
        .post(&token, &format!("/v1/scans/{scan_id}/finish"), json!({}))
        .await;
    assert_eq!(status, StatusCode::CONFLICT);
}

#[tokio::test]
async fn scene_is_404_until_a_room_exists() {
    let app = TestApp::start().await;
    let token = app.register("scene@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let (status, _) = app.get(&token, &format!("/v1/scans/{scan_id}/scene")).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    let other = app.register("scene2@example.com").await;
    send_room(&app, &token, &scan_id, door_room_at("r1", 0.9, 0), vec![]).await;
    let (status, _) = app.get(&other, &format!("/v1/scans/{scan_id}/scene")).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}
