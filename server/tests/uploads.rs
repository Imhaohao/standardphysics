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

#[tokio::test]
async fn aborting_an_in_progress_mesh_upload_releases_it() {
    let app = TestApp::start().await;
    let token = app.register("release@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let data = payload(6 * MIB);
    let upload = create_upload(&app, &token, &scan_id, data.len()).await;
    let upload_id = upload["id"].as_str().unwrap();
    let urls = presign(&app, &token, &scan_id, upload_id, &[1]).await;
    put_part(&app, &urls[0], data[..5 * MIB].to_vec()).await;
    assert_eq!(app.s3.open_multipart_count(), 1);

    let abort = format!("/v1/scans/{scan_id}/uploads/{upload_id}/abort");
    let (status, _) = app.post(&token, &abort, json!({})).await;
    assert_eq!(status, StatusCode::NO_CONTENT);
    assert_eq!(app.s3.open_multipart_count(), 0, "multipart is released");
    assert!(app.s3.object_keys().is_empty());

    let (status, _) = app.post(&token, &abort, json!({})).await;
    assert_eq!(
        status,
        StatusCode::NO_CONTENT,
        "aborting twice is idempotent"
    );
    let (_, status_body) = app
        .get(&token, &format!("/v1/scans/{scan_id}/uploads/{upload_id}"))
        .await;
    assert_eq!(status_body["upload"]["state"], "aborted");
    let complete = format!("/v1/scans/{scan_id}/uploads/{upload_id}/complete");
    let (status, _) = app
        .post(&token, &complete, json!({"sha256": sha256_hex(&data)}))
        .await;
    assert_eq!(status, StatusCode::CONFLICT);
}

#[tokio::test]
async fn a_losing_concurrent_complete_never_records_a_second_artifact() {
    let app = TestApp::start().await;
    let token = app.register("race@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let data = payload(1000);
    let artifact_id = common::upload_artifact(&app, &token, &scan_id, "photo", &data).await;
    let scan = uuid::Uuid::parse_str(&scan_id).unwrap();
    let (upload_id,): (uuid::Uuid,) = sqlx::query_as("SELECT id FROM uploads WHERE scan_id = $1")
        .bind(scan)
        .fetch_one(&app.db)
        .await
        .unwrap();
    // A second request that read the upload as `open` before the first one finished.
    let mut stale = sp_server::uploads::repo::get_upload(&app.db, scan, upload_id)
        .await
        .unwrap();
    stale.state = "open".into();
    let again = sp_server::uploads::repo::finish_upload_with_artifact(
        &app.db,
        &stale,
        &sha256_hex(&data),
        true,
    )
    .await
    .unwrap();
    assert_eq!(again.id.to_string(), artifact_id);
    let (_, artifacts) = app
        .get(&token, &format!("/v1/scans/{scan_id}/artifacts"))
        .await;
    assert_eq!(artifacts.as_array().unwrap().len(), 1);
}

#[tokio::test]
async fn sha256_verified_is_true_only_when_the_server_hashed_the_object() {
    let app = TestApp::start_with(common::TestOptions {
        verify_max_bytes: Some(1024),
        ..Default::default()
    })
    .await;
    let token = app.register("verified@example.com").await;
    let scan_id = app.create_scan(&token).await;

    let small = payload(1000);
    let (_, small_artifact) =
        common::try_upload_artifact(&app, &token, &scan_id, "photo", &small).await;
    assert_eq!(small_artifact["sha256_verified"], true);

    let large = payload(2000);
    let (status, large_artifact) =
        common::try_upload_artifact(&app, &token, &scan_id, "photo", &large).await;
    assert_eq!(status, StatusCode::OK, "{large_artifact}");
    assert_eq!(large_artifact["sha256"], sha256_hex(&large));
    assert_eq!(large_artifact["sha256_verified"], false);

    let (_, listed) = app
        .get(&token, &format!("/v1/scans/{scan_id}/artifacts"))
        .await;
    let flags: Vec<bool> = listed
        .as_array()
        .unwrap()
        .iter()
        .map(|a| a["sha256_verified"].as_bool().unwrap())
        .collect();
    assert_eq!(flags, vec![true, false]);
}

#[tokio::test]
async fn complete_recovers_when_storage_finished_but_the_database_did_not() {
    let app = TestApp::start().await;
    let token = app.register("recover@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let data = payload(MIB);
    let upload = create_upload(&app, &token, &scan_id, data.len()).await;
    let upload_id = upload["id"].as_str().unwrap();
    let urls = presign(&app, &token, &scan_id, upload_id, &[1]).await;
    put_part(&app, &urls[0], data.clone()).await;

    let scan = uuid::Uuid::parse_str(&scan_id).unwrap();
    let record = sp_server::uploads::repo::get_upload(&app.db, scan, upload_id.parse().unwrap())
        .await
        .unwrap();
    let parts = app
        .state
        .storage
        .list_parts(&record.s3_key, &record.s3_upload_id)
        .await
        .unwrap();
    let etags: Vec<(i32, String)> = parts.into_iter().map(|p| (p.part_number, p.etag)).collect();
    app.state
        .storage
        .complete_multipart(&record.s3_key, &record.s3_upload_id, &etags)
        .await
        .unwrap();
    assert_eq!(app.s3.open_multipart_count(), 0);

    let path = format!("/v1/scans/{scan_id}/uploads/{upload_id}/complete");
    let (status, artifact) = app
        .post(&token, &path, json!({"sha256": sha256_hex(&data)}))
        .await;
    assert_eq!(status, StatusCode::OK, "{artifact}");
    assert_eq!(artifact["size_bytes"], data.len());
    assert_eq!(artifact["sha256_verified"], true);
}

#[tokio::test]
async fn complete_with_a_vanished_upload_and_no_object_conflicts() {
    let app = TestApp::start().await;
    let token = app.register("vanished@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let upload = create_upload(&app, &token, &scan_id, MIB).await;
    let upload_id = upload["id"].as_str().unwrap();
    app.s3.store.lock().unwrap().uploads.clear();
    let path = format!("/v1/scans/{scan_id}/uploads/{upload_id}/complete");
    let (status, _) = app
        .post(&token, &path, json!({"sha256": sha256_hex(b"x")}))
        .await;
    assert_eq!(status, StatusCode::CONFLICT);
}
