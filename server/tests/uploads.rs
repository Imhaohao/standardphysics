mod common;

use common::{sha256_hex, TestApp};
use reqwest::StatusCode;
use serde_json::{json, Value};

const MIB: usize = 1024 * 1024;

fn payload(len: usize) -> Vec<u8> {
    (0..len).map(|i| (i % 251) as u8).collect()
}

async fn create_upload(app: &TestApp, token: &str, scan_id: &str, size: usize) -> Value {
    let body = json!({
        "kind": "mesh", "filename": "room 1.bin", "content_type": "application/octet-stream",
        "size_bytes": size, "part_size": 5 * MIB,
    });
    let (status, upload) = app
        .post(token, &format!("/v1/scans/{scan_id}/uploads"), body)
        .await;
    assert_eq!(status, StatusCode::CREATED, "{upload}");
    upload
}

async fn presign(
    app: &TestApp,
    token: &str,
    scan_id: &str,
    upload_id: &str,
    parts: &[i32],
) -> Vec<Value> {
    let path = format!("/v1/scans/{scan_id}/uploads/{upload_id}/parts");
    let (status, body) = app.post(token, &path, json!({"part_numbers": parts})).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    body["parts"].as_array().unwrap().clone()
}

async fn put_part(app: &TestApp, presigned: &Value, data: Vec<u8>) {
    let url = presigned["url"].as_str().unwrap();
    assert!(
        url.contains("X-Amz-Signature"),
        "url is not presigned: {url}"
    );
    let mut req = app.http.put(url).body(data);
    for (name, value) in presigned["headers"]
        .as_array()
        .unwrap()
        .iter()
        .map(|h| (h[0].as_str().unwrap(), h[1].as_str().unwrap()))
    {
        req = req.header(name, value);
    }
    let resp = req.send().await.unwrap();
    assert!(
        resp.status().is_success(),
        "part upload failed: {}",
        resp.status()
    );
}

#[tokio::test]
async fn multipart_upload_resumes_and_records_sha256() {
    let app = TestApp::start().await;
    let token = app.register("up@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let data = payload(12 * MIB);
    let upload = create_upload(&app, &token, &scan_id, data.len()).await;
    let upload_id = upload["id"].as_str().unwrap();
    assert_eq!(upload["part_count"], 3);

    let chunk = |n: usize| data[(n - 1) * 5 * MIB..(n * 5 * MIB).min(data.len())].to_vec();
    let urls = presign(&app, &token, &scan_id, upload_id, &[1, 2, 3]).await;
    put_part(&app, &urls[0], chunk(1)).await;
    put_part(&app, &urls[2], chunk(3)).await;

    let status_path = format!("/v1/scans/{scan_id}/uploads/{upload_id}");
    let (_, status) = app.get(&token, &status_path).await;
    let done: Vec<i64> = status["uploaded_parts"]
        .as_array()
        .unwrap()
        .iter()
        .map(|p| p["part_number"].as_i64().unwrap())
        .collect();
    assert_eq!(
        done,
        vec![1, 3],
        "phone resumes by uploading only the missing part"
    );

    let complete_path = format!("/v1/scans/{scan_id}/uploads/{upload_id}/complete");
    let (status, body) = app
        .post(&token, &complete_path, json!({"sha256": sha256_hex(&data)}))
        .await;
    assert_eq!(
        status,
        StatusCode::UNPROCESSABLE_ENTITY,
        "incomplete upload must not complete: {body}"
    );
    assert!(body["message"].as_str().unwrap().contains("[2]"));

    put_part(&app, &urls[1], chunk(2)).await;
    let (status, artifact) = app
        .post(
            &token,
            &complete_path,
            json!({"sha256": sha256_hex(&data).to_uppercase()}),
        )
        .await;
    assert_eq!(status, StatusCode::OK, "{artifact}");
    assert_eq!(artifact["sha256"], sha256_hex(&data));
    assert_eq!(artifact["size_bytes"], data.len());

    let key = app.s3.object_keys().into_iter().next().unwrap();
    assert!(key.starts_with(&format!("scans/{scan_id}/mesh/")));
    assert_eq!(app.s3.object(&key).unwrap(), data);

    let (status, again) = app
        .post(&token, &complete_path, json!({"sha256": sha256_hex(&data)}))
        .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(
        again["id"], artifact["id"],
        "completing twice is idempotent"
    );

    let (_, artifacts) = app
        .get(&token, &format!("/v1/scans/{scan_id}/artifacts"))
        .await;
    assert_eq!(artifacts.as_array().unwrap().len(), 1);
}

#[tokio::test]
async fn wrong_sha256_discards_the_object() {
    let app = TestApp::start().await;
    let token = app.register("sha@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let data = payload(MIB);
    let upload = create_upload(&app, &token, &scan_id, data.len()).await;
    let upload_id = upload["id"].as_str().unwrap();
    let urls = presign(&app, &token, &scan_id, upload_id, &[1]).await;
    put_part(&app, &urls[0], data).await;

    let path = format!("/v1/scans/{scan_id}/uploads/{upload_id}/complete");
    let (status, _) = app
        .post(
            &token,
            &path,
            json!({"sha256": sha256_hex(b"something else")}),
        )
        .await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(app.s3.object_keys().is_empty());
    let (_, artifacts) = app
        .get(&token, &format!("/v1/scans/{scan_id}/artifacts"))
        .await;
    assert!(artifacts.as_array().unwrap().is_empty());
    let (status, _) = app
        .post(&token, &path, json!({"sha256": sha256_hex(b"x")}))
        .await;
    assert_eq!(status, StatusCode::CONFLICT);
}

#[tokio::test]
async fn abort_validates_inputs_and_closes_the_upload() {
    let app = TestApp::start().await;
    let token = app.register("abort@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let uploads = format!("/v1/scans/{scan_id}/uploads");

    for bad in [
        json!({"kind": "Bad Kind", "filename": "a", "content_type": "x/y", "size_bytes": 10}),
        json!({"kind": "mesh", "filename": "a", "content_type": "x/y", "size_bytes": 0}),
        json!({"kind": "mesh", "filename": "a", "content_type": "x/y", "size_bytes": 10, "part_size": 1024}),
    ] {
        let (status, _) = app.post(&token, &uploads, bad).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
    }

    let upload = create_upload(&app, &token, &scan_id, 6 * MIB).await;
    let upload_id = upload["id"].as_str().unwrap();
    let (status, _) = app
        .post(
            &token,
            &format!("{uploads}/{upload_id}/parts"),
            json!({"part_numbers": [99]}),
        )
        .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);

    let (status, _) = app
        .post(&token, &format!("{uploads}/{upload_id}/abort"), json!({}))
        .await;
    assert_eq!(status, StatusCode::NO_CONTENT);
    let (status, _) = app
        .post(
            &token,
            &format!("{uploads}/{upload_id}/parts"),
            json!({"part_numbers": [1]}),
        )
        .await;
    assert_eq!(status, StatusCode::CONFLICT);
}

#[tokio::test]
async fn presigned_urls_use_the_single_configured_public_host() {
    let app = TestApp::start_with(common::TestOptions {
        public_host_alias: true,
        ..Default::default()
    })
    .await;
    let token = app.register("host@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let upload = create_upload(&app, &token, &scan_id, MIB).await;
    let upload_id = upload["id"].as_str().unwrap();
    let path = format!("/v1/scans/{scan_id}/uploads/{upload_id}/parts");
    let (_, body) = app.post(&token, &path, json!({"part_numbers": [1]})).await;
    let host = body["host"].as_str().unwrap();
    assert!(host.starts_with("localhost:"), "{host}");
    let url = body["parts"][0]["url"].as_str().unwrap();
    assert!(
        url.starts_with(&format!("http://{host}/sp-test/scans/")),
        "path-style on the public host: {url}"
    );

    let presigned = &body["parts"][0];
    put_part(&app, presigned, payload(MIB)).await;
}

#[tokio::test]
async fn presign_response_names_the_host_to_allowlist() {
    let app = TestApp::start().await;
    let token = app.register("host2@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let upload = create_upload(&app, &token, &scan_id, MIB).await;
    let path = format!(
        "/v1/scans/{scan_id}/uploads/{}/parts",
        upload["id"].as_str().unwrap()
    );
    let (_, body) = app.post(&token, &path, json!({"part_numbers": [1]})).await;
    let url = body["parts"][0]["url"].as_str().unwrap();
    assert!(url.contains(body["host"].as_str().unwrap()));
}
