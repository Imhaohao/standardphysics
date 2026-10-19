mod common;

use common::TestApp;
use reqwest::{Method, StatusCode};

#[tokio::test]
async fn health_and_readiness() {
    let app = TestApp::start().await;
    let (status, body) = app.request(Method::GET, None, "/health", None).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "ok");
    let (status, body) = app.request(Method::GET, None, "/health/ready", None).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["database"], true);
    assert_eq!(body["storage"], true);
}

#[tokio::test]
async fn served_openapi_matches_the_committed_file() {
    let app = TestApp::start().await;
    let (status, served) = app
        .request(Method::GET, None, "/v1/openapi.json", None)
        .await;
    assert_eq!(status, StatusCode::OK);
    let committed: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/openapi.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(
        served, committed,
        "run `cargo run -- openapi > openapi.json` to refresh"
    );
    assert!(served["paths"]["/v1/scans/{scan_id}/finish"].is_object());
}
