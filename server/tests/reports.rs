mod common;

use std::sync::atomic::Ordering;

use common::{
    connect_live, door_room_at, next_of_type, send_json, upload_artifact, TestApp, TestOptions,
};
use reqwest::{Method, StatusCode};
use serde_json::{json, Value};

async fn finished_scan(app: &TestApp, token: &str, observations: Vec<Value>) -> (String, Value) {
    let scan_id = app.create_scan(token).await;
    let mut phone = connect_live(app, token, &scan_id, "writer").await;
    next_of_type(&mut phone, "hello").await;
    let room = door_room_at("r1", 0.9, 1);
    let message = json!({
        "type": "room", "room_id": room["identifier"], "final": true,
        "captured_room": room, "observations": observations,
    });
    send_json(&mut phone, message).await;
    next_of_type(&mut phone, "findings").await;
    let (status, report) = app
        .post(token, &format!("/v1/scans/{scan_id}/finish"), json!({}))
        .await;
    assert_eq!(status, StatusCode::OK, "{report}");
    (scan_id, report)
}

fn first_yes_no_question(report: &Value) -> Value {
    report["findings"]
        .as_array()
        .unwrap()
        .iter()
        .find(|f| f["ask"]["value_type"] == "boolean")
        .cloned()
        .expect("the report asks at least one yes/no question")
}

fn finding_for<'a>(report: &'a Value, rule_id: &Value, subject_id: &Value) -> &'a Value {
    report["findings"]
        .as_array()
        .unwrap()
        .iter()
        .find(|f| &f["rule_id"] == rule_id && &f["subject_id"] == subject_id)
        .expect("the finding is still reported")
}

async fn put_answers(
    app: &TestApp,
    token: &str,
    scan_id: &str,
    answers: Value,
) -> (StatusCode, Value) {
    app.request(
        Method::PUT,
        Some(token),
        &format!("/v1/scans/{scan_id}/answers"),
        Some(json!({ "answers": answers })),
    )
    .await
}

#[tokio::test]
async fn answering_a_question_re_evaluates_the_report() {
    let app = TestApp::start().await;
    let token = app.register("answers@example.com").await;
    let (scan_id, report) = finished_scan(&app, &token, vec![]).await;
    let question = first_yes_no_question(&report);
    let ask = &question["ask"];
    assert_eq!(question["status"], "needs_info");
    assert!(!ask["prompt"].as_str().unwrap().is_empty());

    let answer = json!([{"subject_id": ask["subject_id"], "metric": ask["metric"], "value": true}]);
    let (status, updated) = put_answers(&app, &token, &scan_id, answer).await;
    assert_eq!(status, StatusCode::OK, "{updated}");
    let settled = finding_for(&updated, &question["rule_id"], &question["subject_id"]);
    assert!(settled["ask"].is_null(), "{settled}");
    assert_ne!(updated["assessment_id"], report["assessment_id"]);

    let (_, latest) = app
        .get(&token, &format!("/v1/scans/{scan_id}/assessment"))
        .await;
    assert_eq!(latest["assessment_id"], updated["assessment_id"]);
    let (_, saved) = app
        .get(&token, &format!("/v1/scans/{scan_id}/answers"))
        .await;
    assert_eq!(saved.as_array().unwrap().len(), 1);
    assert_eq!(saved[0]["value"], true);

    let clear = json!([{"subject_id": ask["subject_id"], "metric": ask["metric"], "value": null}]);
    let (status, reopened) = put_answers(&app, &token, &scan_id, clear).await;
    assert_eq!(status, StatusCode::OK);
    let again = finding_for(&reopened, &question["rule_id"], &question["subject_id"]);
    assert_eq!(again["ask"], question["ask"]);
    let (_, saved) = app
        .get(&token, &format!("/v1/scans/{scan_id}/answers"))
        .await;
    assert!(saved.as_array().unwrap().is_empty());
}

#[tokio::test]
async fn answers_are_checked_and_need_a_finished_scan() {
    let app = TestApp::start().await;
    let token = app.register("checks@example.com").await;
    let unfinished = app.create_scan(&token).await;
    let answer =
        json!([{"subject_id": "site", "metric": "site.construction_era", "value": "post_2012"}]);
    let (status, _) = put_answers(&app, &token, &unfinished, answer).await;
    assert_eq!(status, StatusCode::CONFLICT);

    let (scan_id, _) = finished_scan(&app, &token, vec![]).await;
    for bad in [
        json!([{"subject_id": "site", "metric": "no.such_metric", "value": true}]),
        json!([{"subject_id": "", "metric": "site.construction_era", "value": "x"}]),
        json!([{"subject_id": "site", "metric": "site.construction_era", "value": {"a": 1}}]),
    ] {
        let (status, body) = put_answers(&app, &token, &scan_id, bad.clone()).await;
        assert_eq!(status, StatusCode::BAD_REQUEST, "{bad} -> {body}");
    }
    let other = app.register("other@example.com").await;
    let answer =
        json!([{"subject_id": "site", "metric": "site.construction_era", "value": "post_2012"}]);
    let (status, _) = put_answers(&app, &other, &scan_id, answer).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn re_assessment_keeps_vision_labels_without_calling_the_api_again() {
    let app = TestApp::start_with(TestOptions::default()).await;
    let token = app.register("relabel@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let crop = upload_artifact(&app, &token, &scan_id, "crop", b"jpeg").await;
    let scan_id = {
        let mut phone = connect_live(&app, &token, &scan_id, "writer").await;
        next_of_type(&mut phone, "hello").await;
        let room = door_room_at("r1", 0.9, 1);
        let observation = json!({"id": "o1", "crop_artifact_id": crop,
            "center": {"x": 1.0, "y": 0.5, "z": 1.0}, "size": {"x": 0.5, "y": 1.0, "z": 0.5}});
        send_json(
            &mut phone,
            json!({"type": "room", "room_id": room["identifier"], "final": true,
            "captured_room": room, "observations": [observation]}),
        )
        .await;
        next_of_type(&mut phone, "findings").await;
        scan_id
    };
    let (status, report) = app
        .post(&token, &format!("/v1/scans/{scan_id}/finish"), json!({}))
        .await;
    assert_eq!(status, StatusCode::OK, "{report}");
    assert_eq!(report["labelled_by_vision"], 1);
    let calls = app.label_api.calls.load(Ordering::SeqCst);

    let answer =
        json!([{"subject_id": "site", "metric": "site.construction_era", "value": "post_2012"}]);
    let (status, updated) = put_answers(&app, &token, &scan_id, answer).await;
    assert_eq!(status, StatusCode::OK, "{updated}");
    assert_eq!(app.label_api.calls.load(Ordering::SeqCst), calls);
    assert_eq!(updated["unlabelled_objects"], 0);
    assert!(updated["findings"]
        .as_array()
        .unwrap()
        .iter()
        .all(|f| f["rule_id"] != "label.unresolved"));
}

#[tokio::test]
async fn scans_can_be_renamed() {
    let app = TestApp::start().await;
    let token = app.register("rename@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let path = format!("/v1/scans/{scan_id}");
    let rename = |body: Value| app.request(Method::PATCH, Some(&token), &path, Some(body));

    let (status, scan) = rename(json!({"name": "  Corner cafe ", "site_name": "Main St"})).await;
    assert_eq!(status, StatusCode::OK, "{scan}");
    assert_eq!(scan["name"], "Corner cafe");
    assert_eq!(scan["site_name"], "Main St");
    let (_, scan) = rename(json!({"name": "Cafe"})).await;
    assert_eq!(
        scan["site_name"], "Main St",
        "a missing field is left alone"
    );
    let (_, scan) = rename(json!({"site_name": null})).await;
    assert!(scan["site_name"].is_null());
    assert_eq!(scan["name"], "Cafe");
    let (status, _) = rename(json!({"name": "   "})).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn deleting_a_scan_removes_it_and_its_files() {
    let app = TestApp::start().await;
    let token = app.register("delete@example.com").await;
    let scan_id = app.create_scan(&token).await;
    upload_artifact(&app, &token, &scan_id, "mesh", b"mesh-bytes").await;
    assert!(!app.s3.object_keys().is_empty());

    let other = app.register("intruder@example.com").await;
    let path = format!("/v1/scans/{scan_id}");
    let (status, _) = app.request(Method::DELETE, Some(&other), &path, None).await;
    assert_eq!(status, StatusCode::NOT_FOUND);

    let (status, _) = app.request(Method::DELETE, Some(&token), &path, None).await;
    assert_eq!(status, StatusCode::NO_CONTENT);
    let (status, _) = app.get(&token, &path).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    assert!(
        app.s3.object_keys().is_empty(),
        "{:?}",
        app.s3.object_keys()
    );
}

#[tokio::test]
async fn share_links_are_read_only_and_can_be_revoked() {
    let app = TestApp::start().await;
    let token = app.register("share@example.com").await;
    let (scan_id, report) = finished_scan(&app, &token, vec![]).await;

    let (status, share) = app
        .post(&token, &format!("/v1/scans/{scan_id}/shares"), json!({}))
        .await;
    assert_eq!(status, StatusCode::CREATED, "{share}");
    let link = share["token"].as_str().unwrap();
    assert_eq!(link.len(), 43);

    let public = format!("/v1/shared/{link}");
    let (status, shared) = app.request(Method::GET, None, &public, None).await;
    assert_eq!(status, StatusCode::OK, "{shared}");
    assert_eq!(shared["scan"]["id"], scan_id.as_str());
    assert_eq!(shared["report"]["assessment_id"], report["assessment_id"]);
    assert_eq!(shared["scene"]["rooms"].as_array().unwrap().len(), 1);

    let (_, listed) = app
        .get(&token, &format!("/v1/scans/{scan_id}/shares"))
        .await;
    assert_eq!(listed[0]["token"], link);
    let other = app.register("stranger@example.com").await;
    let revoke = format!("/v1/scans/{scan_id}/shares/{link}");
    let (status, _) = app
        .request(Method::DELETE, Some(&other), &revoke, None)
        .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    let (status, _) = app
        .request(Method::DELETE, Some(&token), &revoke, None)
        .await;
    assert_eq!(status, StatusCode::NO_CONTENT);
    let (status, _) = app.request(Method::GET, None, &public, None).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    let (status, _) = app
        .request(Method::GET, None, "/v1/shared/not-a-token", None)
        .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn deleting_the_account_removes_everything() {
    let app = TestApp::start().await;
    let token = app.register("leaving@example.com").await;
    let scan_id = app.create_scan(&token).await;
    upload_artifact(&app, &token, &scan_id, "mesh", b"mesh-bytes").await;
    let (status, _) = app
        .request(Method::DELETE, Some(&token), "/v1/me", None)
        .await;
    assert_eq!(status, StatusCode::NO_CONTENT);
    let (status, _) = app.get(&token, "/v1/me").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert!(app.s3.object_keys().is_empty());
    let scans: (i64,) = sqlx::query_as("SELECT count(*) FROM scans")
        .fetch_one(&app.db)
        .await
        .unwrap();
    assert_eq!(scans.0, 0);
    let again = app
        .request(
            Method::POST,
            None,
            "/v1/auth/register",
            Some(json!({"email": "leaving@example.com", "password": "correct horse battery"})),
        )
        .await;
    assert_eq!(again.0, StatusCode::CREATED, "the email is free again");
}
