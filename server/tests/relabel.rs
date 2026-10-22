mod common;

use std::sync::atomic::Ordering;

use common::{
    connect_live, door_room_at, findings_for, next_of_type, send_json, upload_artifact, TestApp,
    TestOptions,
};
use reqwest::{Method, StatusCode};
use serde_json::{json, Value};

const COUNTER: &str = "5D1C0C55-4C8E-4F49-9C1B-6A3E2B7C0F11";
const OVERRIDE_METRIC: &str = "object.category_override";

/// A room with one RoomPlan `storage` box 38 in high and 6 ft wide: an ordering counter as
/// RoomPlan reports it.
fn room_with_counter() -> Value {
    let mut room = door_room_at("r1", 0.95, 1);
    room["objects"] = json!([{
        "identifier": COUNTER,
        "category": {"storage": {}},
        "confidence": {"high": {}},
        "attributes": {},
        "dimensions": [1.83, 0.965, 0.6],
        "transform": [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 6.5, 0.4825, 0.5, 1.],
        "story": 0,
    }]);
    room
}

async fn send_room(app: &TestApp, token: &str, scan_id: &str, observations: Vec<Value>) {
    let mut phone = connect_live(app, token, scan_id, "writer").await;
    next_of_type(&mut phone, "hello").await;
    let room = room_with_counter();
    let message = json!({
        "type": "room", "room_id": "r1", "final": true,
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

/// A finished scan whose counter was sent with a crop for relabelling.
async fn finished_with_crop(app: &TestApp, email: &str, crop: &[u8]) -> (String, String, Value) {
    let token = app.register(email).await;
    let scan_id = app.create_scan(&token).await;
    let crop_id = upload_artifact(app, &token, &scan_id, "crop", crop).await;
    let observation = json!({
        "id": format!("relabel-{COUNTER}"),
        "relabel_object_id": COUNTER,
        "crop_artifact_id": crop_id,
    });
    send_room(app, &token, &scan_id, vec![observation]).await;
    let report = finish(app, &token, &scan_id).await;
    (token, scan_id, report)
}

fn rule_ids(report: &Value) -> Vec<String> {
    findings_for(&report["findings"], COUNTER)
        .iter()
        .map(|f| f["rule_id"].as_str().unwrap().to_string())
        .collect()
}

fn category_question(report: &Value) -> Option<Value> {
    findings_for(&report["findings"], COUNTER)
        .into_iter()
        .find(|f| f["ask"]["metric"] == OVERRIDE_METRIC)
        .cloned()
}

async fn object_category(app: &TestApp, token: &str, scan_id: &str) -> Value {
    let (status, scene) = app.get(token, &format!("/v1/scans/{scan_id}/scene")).await;
    assert_eq!(status, StatusCode::OK);
    scene["rooms"][0]["objects"]
        .as_array()
        .unwrap()
        .iter()
        .find(|o| o["id"] == COUNTER)
        .cloned()
        .expect("the counter is in the scene")
}

#[tokio::test]
async fn a_confident_relabel_checks_the_counter_as_a_sales_counter() {
    let app = TestApp::start().await;
    let (token, scan_id, report) =
        finished_with_crop(&app, "relabel@example.com", b"counter").await;

    assert_eq!(app.label_api.relabel_calls.load(Ordering::SeqCst), 1);
    let asked = app.label_api.last_relabel_text.lock().unwrap().clone();
    assert!(asked.contains("sales_counter"), "{asked}");
    assert!(
        asked.contains("The scanner called it storage. Its top is 38 in"),
        "{asked}"
    );

    let rules = rule_ids(&report);
    assert!(
        rules.iter().any(|r| r.starts_with("ADA-904.4")),
        "{rules:?}"
    );
    assert!(category_question(&report).is_none());
    assert_eq!(report["labelled_by_vision"], 1);

    let counter = object_category(&app, &token, &scan_id).await;
    assert_eq!(counter["category"], "sales_counter");
    assert_eq!(counter["attributes"]["built_in"], "true");
    assert_eq!(counter["attributes"]["label_source"], "vision");
    assert_eq!(counter["attributes"]["scanned_category"], "storage");
}

#[tokio::test]
async fn an_unsure_relabel_asks_the_owner_and_the_answer_changes_the_category() {
    let app = TestApp::start().await;
    *app.label_api.relabel_reply.lock().unwrap() =
        json!({"category": "sales_counter", "built_in": true, "confidence": 0.3});
    let (token, scan_id, report) = finished_with_crop(&app, "unsure@example.com", b"blurry").await;

    let question = category_question(&report).expect("the owner is asked what the counter is");
    assert_eq!(question["status"], "needs_info");
    assert_eq!(question["ask"]["value_type"], "enum");
    assert_eq!(question["ask"]["subject_id"], COUNTER);
    let options: Vec<&str> = question["ask"]["options"]
        .as_array()
        .unwrap()
        .iter()
        .map(|o| o.as_str().unwrap())
        .collect();
    assert!(options.contains(&"A counter where customers order or pay"));
    assert!(options.contains(&"Something else"));
    assert!(!rule_ids(&report).iter().any(|r| r.starts_with("ADA-904.4")));
    assert_eq!(
        object_category(&app, &token, &scan_id).await["category"],
        "storage"
    );

    let answer = json!({"answers": [{
        "subject_id": COUNTER, "metric": OVERRIDE_METRIC,
        "value": "A counter where customers order or pay",
    }]});
    let (status, updated) = app
        .request(
            Method::PUT,
            Some(&token),
            &format!("/v1/scans/{scan_id}/answers"),
            Some(answer),
        )
        .await;
    assert_eq!(status, StatusCode::OK, "{updated}");
    assert!(
        category_question(&updated).is_none(),
        "an answered question is not asked again"
    );
    let rules = rule_ids(&updated);
    assert!(
        rules.iter().any(|r| r.starts_with("ADA-904.4")),
        "{rules:?}"
    );
    assert_eq!(
        app.label_api.relabel_calls.load(Ordering::SeqCst),
        1,
        "re-assessment reuses labels"
    );

    let counter = object_category(&app, &token, &scan_id).await;
    assert_eq!(counter["category"], "sales_counter");
    assert_eq!(counter["attributes"]["label_source"], "owner");
}

#[tokio::test]
async fn without_a_label_key_the_owner_is_asked() {
    let app = TestApp::start_with(TestOptions {
        label_key: None,
        ..TestOptions::default()
    })
    .await;
    let (_, _, report) = finished_with_crop(&app, "nokey-relabel@example.com", b"counter").await;
    assert_eq!(app.label_api.calls.load(Ordering::SeqCst), 0);
    assert!(category_question(&report).is_some());
}

#[tokio::test]
async fn the_same_crop_is_relabelled_once_across_scans() {
    let app = TestApp::start().await;
    finished_with_crop(&app, "cache-a@example.com", b"same-counter").await;
    let (_, _, second) = finished_with_crop(&app, "cache-b@example.com", b"same-counter").await;
    assert_eq!(app.label_api.relabel_calls.load(Ordering::SeqCst), 1);
    assert!(rule_ids(&second).iter().any(|r| r.starts_with("ADA-904.4")));
}

#[tokio::test]
async fn relabel_requests_are_not_detector_objects() {
    let app = TestApp::start().await;
    let (_, _, report) = finished_with_crop(&app, "notdetector@example.com", b"counter").await;
    assert_eq!(report["unlabelled_objects"], 0);
    let calls = app.label_api.calls.load(Ordering::SeqCst);
    assert_eq!(calls, 1, "only the relabel question went to the model");
}
