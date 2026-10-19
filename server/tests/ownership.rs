mod common;

use common::TestApp;
use reqwest::StatusCode;
use serde_json::json;

#[tokio::test]
async fn scans_are_listed_per_user_and_foreign_scans_are_404() {
    let app = TestApp::start().await;
    let alice = app.register("alice@example.com").await;
    let bob = app.register("bob@example.com").await;
    let scan_id = app.create_scan(&alice).await;

    let (status, mine) = app.get(&alice, "/v1/scans").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(mine.as_array().unwrap().len(), 1);
    let (_, theirs) = app.get(&bob, "/v1/scans").await;
    assert!(theirs.as_array().unwrap().is_empty());

    let (status, scan) = app.get(&alice, &format!("/v1/scans/{scan_id}")).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(scan["status"], "capturing");

    let upload_body = json!({"kind": "mesh", "filename": "a.bin", "content_type": "application/octet-stream", "size_bytes": 10});
    let upload_path = format!("/v1/scans/{scan_id}/uploads");
    let (_, upload) = app.post(&alice, &upload_path, upload_body.clone()).await;
    let upload_id = upload["id"].as_str().unwrap();
    let base = format!("/v1/scans/{scan_id}");

    for path in [
        base.clone(),
        format!("{base}/assessment"),
        format!("{base}/artifacts"),
        format!("{base}/uploads/{upload_id}"),
    ] {
        let (status, _) = app.get(&bob, &path).await;
        assert_eq!(status, StatusCode::NOT_FOUND, "GET {path}");
    }
    for (path, body) in [
        (format!("{base}/finish"), json!({})),
        (format!("{base}/uploads"), upload_body),
        (
            format!("{base}/uploads/{upload_id}/parts"),
            json!({"part_numbers": [1]}),
        ),
        (
            format!("{base}/uploads/{upload_id}/complete"),
            json!({"sha256": "0".repeat(64)}),
        ),
        (format!("{base}/uploads/{upload_id}/abort"), json!({})),
    ] {
        let (status, _) = app.post(&bob, &path, body).await;
        assert_eq!(status, StatusCode::NOT_FOUND, "POST {path}");
    }

    let (status, _) = app
        .get(&alice, &format!("/v1/scans/{}", uuid::Uuid::new_v4()))
        .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn foreign_websocket_is_refused() {
    let app = TestApp::start().await;
    let alice = app.register("alice2@example.com").await;
    let bob = app.register("bob2@example.com").await;
    let scan_id = app.create_scan(&alice).await;
    let err = common::try_connect_live(&app, Some(&bob), &format!("/v1/scans/{scan_id}/live"))
        .await
        .err()
        .unwrap();
    assert!(err.to_string().contains("404"), "{err}");
}
