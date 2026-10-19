mod common;

use common::{next_of_type, try_connect_live, TestApp};
use reqwest::StatusCode;
use serde_json::json;

async fn ticket_for(app: &TestApp, token: &str, scan_id: &str) -> String {
    let (status, body) = app
        .post(
            token,
            &format!("/v1/scans/{scan_id}/live-ticket"),
            json!({}),
        )
        .await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["expires_in_secs"], 30);
    body["ticket"].as_str().unwrap().to_string()
}

fn status_of(err: tokio_tungstenite::tungstenite::Error) -> u16 {
    match err {
        tokio_tungstenite::tungstenite::Error::Http(response) => response.status().as_u16(),
        other => panic!("unexpected error {other}"),
    }
}

#[tokio::test]
async fn ticket_opens_the_socket_once() {
    let app = TestApp::start().await;
    let token = app.register("t1@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let ticket = ticket_for(&app, &token, &scan_id).await;
    let path = format!("/v1/scans/{scan_id}/live?role=viewer&ticket={ticket}");

    let mut socket = try_connect_live(&app, None, &path).await.unwrap();
    next_of_type(&mut socket, "hello").await;
    let reuse = try_connect_live(&app, None, &path).await.err().unwrap();
    assert_eq!(status_of(reuse), 401, "a ticket is single use");
}

#[tokio::test]
async fn ticket_is_bound_to_its_scan_and_expires() {
    let app = TestApp::start().await;
    let token = app.register("t2@example.com").await;
    let scan_a = app.create_scan(&token).await;
    let scan_b = app.create_scan(&token).await;

    let ticket = ticket_for(&app, &token, &scan_a).await;
    let wrong_scan = try_connect_live(
        &app,
        None,
        &format!("/v1/scans/{scan_b}/live?ticket={ticket}"),
    )
    .await
    .err()
    .unwrap();
    assert_eq!(status_of(wrong_scan), 401);

    let stale = ticket_for(&app, &token, &scan_a).await;
    sqlx::query("UPDATE live_tickets SET expires_at = now() - interval '1 second'")
        .execute(&app.db)
        .await
        .unwrap();
    let expired = try_connect_live(
        &app,
        None,
        &format!("/v1/scans/{scan_a}/live?ticket={stale}"),
    )
    .await
    .err()
    .unwrap();
    assert_eq!(status_of(expired), 401);
}

#[tokio::test]
async fn tickets_are_hashed_and_only_the_owner_can_mint_them() {
    let app = TestApp::start().await;
    let alice = app.register("t3@example.com").await;
    let bob = app.register("t4@example.com").await;
    let scan_id = app.create_scan(&alice).await;
    let (status, _) = app
        .post(&bob, &format!("/v1/scans/{scan_id}/live-ticket"), json!({}))
        .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    let (status, _) = app
        .request(
            reqwest::Method::POST,
            None,
            &format!("/v1/scans/{scan_id}/live-ticket"),
            None,
        )
        .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);

    let ticket = ticket_for(&app, &alice, &scan_id).await;
    let stored: String = sqlx::query_scalar("SELECT ticket_hash FROM live_tickets")
        .fetch_one(&app.db)
        .await
        .unwrap();
    assert_ne!(stored, ticket);
}

#[tokio::test]
async fn session_token_in_the_query_string_is_not_accepted() {
    let app = TestApp::start().await;
    let token = app.register("t5@example.com").await;
    let scan_id = app.create_scan(&token).await;
    let err = try_connect_live(
        &app,
        None,
        &format!("/v1/scans/{scan_id}/live?token={token}"),
    )
    .await
    .err()
    .unwrap();
    assert_eq!(status_of(err), 401);
    let ok = try_connect_live(&app, Some(&token), &format!("/v1/scans/{scan_id}/live")).await;
    assert!(ok.is_ok(), "Authorization header still works for the phone");
}
