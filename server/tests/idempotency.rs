mod common;

use common::TestApp;
use reqwest::{Method, StatusCode};
use serde_json::{json, Value};

async fn post_with_key(
    app: &TestApp,
    token: &str,
    path: &str,
    key: &str,
    body: Value,
) -> (StatusCode, Value, bool) {
    let response = app
        .http
        .request(Method::POST, app.url(path))
        .bearer_auth(token)
        .header("Idempotency-Key", key)
        .json(&body)
        .send()
        .await
        .unwrap();
    let status = response.status();
    let replayed = response.headers().contains_key("idempotent-replayed");
    (
        status,
        response.json().await.unwrap_or(Value::Null),
        replayed,
    )
}

#[tokio::test]
async fn repeated_scan_create_replays_the_first_response() {
    let app = TestApp::start().await;
    let token = app.register("i1@example.com").await;
    let body = json!({"name": "Shop"});
    let (s1, first, replayed1) =
        post_with_key(&app, &token, "/v1/scans", "key-1", body.clone()).await;
    let (s2, second, replayed2) = post_with_key(&app, &token, "/v1/scans", "key-1", body).await;
    assert_eq!((s1, s2), (StatusCode::CREATED, StatusCode::CREATED));
    assert_eq!(first, second);
    assert!(!replayed1 && replayed2);
    let (_, scans) = app.get(&token, "/v1/scans").await;
    assert_eq!(scans.as_array().unwrap().len(), 1);
}

#[tokio::test]
async fn same_key_with_a_different_body_is_a_conflict() {
    let app = TestApp::start().await;
    let token = app.register("i2@example.com").await;
    post_with_key(&app, &token, "/v1/scans", "k", json!({"name": "A"})).await;
    let (status, body, _) =
        post_with_key(&app, &token, "/v1/scans", "k", json!({"name": "B"})).await;
    assert_eq!(status, StatusCode::CONFLICT, "{body}");
}

#[tokio::test]
async fn keys_are_per_user_and_optional() {
    let app = TestApp::start().await;
    let alice = app.register("i3@example.com").await;
    let bob = app.register("i4@example.com").await;
    let (_, a, _) = post_with_key(&app, &alice, "/v1/scans", "shared", json!({"name": "A"})).await;
    let (_, b, replayed) =
        post_with_key(&app, &bob, "/v1/scans", "shared", json!({"name": "A"})).await;
    assert_ne!(a["id"], b["id"]);
    assert!(!replayed);
    app.create_scan(&alice).await;
    app.create_scan(&alice).await;
    let (_, scans) = app.get(&alice, "/v1/scans").await;
    assert_eq!(scans.as_array().unwrap().len(), 3);
}

#[tokio::test]
async fn keys_expire_after_24_hours() {
    let app = TestApp::start().await;
    let token = app.register("i5@example.com").await;
    let (_, first, _) = post_with_key(&app, &token, "/v1/scans", "old", json!({"name": "A"})).await;
    sqlx::query("UPDATE idempotency_keys SET created_at = now() - interval '25 hours'")
        .execute(&app.db)
        .await
        .unwrap();
    let (status, second, replayed) =
        post_with_key(&app, &token, "/v1/scans", "old", json!({"name": "A"})).await;
    assert_eq!(status, StatusCode::CREATED);
    assert!(!replayed);
    assert_ne!(first["id"], second["id"]);
}

#[tokio::test]
async fn failed_requests_do_not_burn_the_key() {
    let app = TestApp::start().await;
    let token = app.register("i6@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let path = format!("/v1/scans/{scan_id}/uploads");
    let bad = json!({"kind": "BAD", "filename": "a", "content_type": "x/y", "size_bytes": 10});
    let (status, _, _) = post_with_key(&app, &token, &path, "u1", bad).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    let good = json!({"kind": "mesh", "filename": "a", "content_type": "x/y", "size_bytes": 10});
    let (status, _, _) = post_with_key(&app, &token, &path, "u1", good).await;
    assert_eq!(status, StatusCode::CREATED);
}

#[tokio::test]
async fn upload_create_is_idempotent_and_makes_one_multipart_upload() {
    let app = TestApp::start().await;
    let token = app.register("i7@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let path = format!("/v1/scans/{scan_id}/uploads");
    let body = json!({"kind": "mesh", "filename": "mesh.spm", "content_type": "application/octet-stream", "size_bytes": 1000});
    let (_, first, _) = post_with_key(&app, &token, &path, "up-1", body.clone()).await;
    let (_, second, replayed) = post_with_key(&app, &token, &path, "up-1", body).await;
    assert_eq!(first["id"], second["id"]);
    assert!(replayed);
    let rows: i64 = sqlx::query_scalar("SELECT count(*) FROM uploads")
        .fetch_one(&app.db)
        .await
        .unwrap();
    assert_eq!(rows, 1);
    assert_eq!(app.s3.store.lock().unwrap().uploads.len(), 1);

    let other_scan = app.create_scan(&token).await;
    let other_path = format!("/v1/scans/{other_scan}/uploads");
    let body = json!({"kind": "mesh", "filename": "mesh.spm", "content_type": "application/octet-stream", "size_bytes": 1000});
    let (_, third, replayed) = post_with_key(&app, &token, &other_path, "up-1", body).await;
    assert_ne!(
        third["id"], first["id"],
        "the same key on another scan is a different request scope"
    );
    assert!(!replayed);
}

#[tokio::test]
async fn a_key_left_in_progress_by_a_dead_request_is_taken_over() {
    let app = TestApp::start().await;
    let token = app.register("i9@example.com").await;
    let body = json!({"name": "Shop"});
    post_with_key(&app, &token, "/v1/scans", "crash", body.clone()).await;
    // The process died after claiming the key and before recording the response.
    sqlx::query("UPDATE idempotency_keys SET status = NULL, response = NULL")
        .execute(&app.db)
        .await
        .unwrap();
    let (status, _, _) = post_with_key(&app, &token, "/v1/scans", "crash", body.clone()).await;
    assert_eq!(
        status,
        StatusCode::CONFLICT,
        "a fresh in-progress key still blocks a duplicate"
    );
    sqlx::query("UPDATE idempotency_keys SET created_at = now() - interval '10 minutes'")
        .execute(&app.db)
        .await
        .unwrap();
    let (status, _, replayed) = post_with_key(&app, &token, "/v1/scans", "crash", body).await;
    assert_eq!(status, StatusCode::CREATED);
    assert!(!replayed);
}
