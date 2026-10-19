mod common;

use common::fakes::BUNDLE_ID;
use common::TestApp;
use reqwest::{Method, StatusCode};
use serde_json::json;

fn apple_claims(sub: &str, exp_offset: i64) -> serde_json::Value {
    let now = chrono::Utc::now().timestamp();
    json!({
        "iss": "https://appleid.apple.com",
        "aud": BUNDLE_ID,
        "sub": sub,
        "email": "apple.user@example.com",
        "exp": now + exp_offset,
        "iat": now,
    })
}

#[tokio::test]
async fn register_login_me_and_logout() {
    let app = TestApp::start().await;
    let token = app.register("Owner@Example.com").await;

    let (status, me) = app.get(&token, "/v1/me").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(me["email"], "owner@example.com");

    let (status, login) = app
        .request(
            Method::POST,
            None,
            "/v1/auth/login",
            Some(json!({"email": "OWNER@example.com", "password": "correct horse battery"})),
        )
        .await;
    assert_eq!(status, StatusCode::OK);
    let second_token = login["token"].as_str().unwrap().to_string();
    assert_ne!(second_token, token);

    let (status, _) = app.post(&second_token, "/v1/auth/logout", json!({})).await;
    assert_eq!(status, StatusCode::NO_CONTENT);
    let (status, _) = app.get(&second_token, "/v1/me").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let (status, _) = app.get(&token, "/v1/me").await;
    assert_eq!(status, StatusCode::OK);
}

#[tokio::test]
async fn session_tokens_are_stored_hashed() {
    let app = TestApp::start().await;
    let token = app.register("hash@example.com").await;
    let stored: Vec<(String,)> = sqlx::query_as("SELECT token_hash FROM sessions")
        .fetch_all(&app.db)
        .await
        .unwrap();
    assert_eq!(stored.len(), 1);
    assert_ne!(stored[0].0, token);
    assert!(!stored[0].0.contains(&token));
}

#[tokio::test]
async fn rejects_duplicate_email_weak_password_and_bad_login() {
    let app = TestApp::start().await;
    app.register("dup@example.com").await;
    let (status, _) = app
        .request(
            Method::POST,
            None,
            "/v1/auth/register",
            Some(json!({"email": "dup@example.com", "password": "another password"})),
        )
        .await;
    assert_eq!(status, StatusCode::CONFLICT);
    let (status, _) = app
        .request(
            Method::POST,
            None,
            "/v1/auth/register",
            Some(json!({"email": "new@example.com", "password": "short"})),
        )
        .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    let (status, _) = app
        .request(
            Method::POST,
            None,
            "/v1/auth/login",
            Some(json!({"email": "dup@example.com", "password": "wrong password"})),
        )
        .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn protected_routes_need_a_valid_token() {
    let app = TestApp::start().await;
    let (status, _) = app.request(Method::GET, None, "/v1/scans", None).await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let (status, _) = app.get("sp_nonsense", "/v1/scans").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn expired_session_is_rejected() {
    let app = TestApp::start().await;
    let token = app.register("old@example.com").await;
    sqlx::query("UPDATE sessions SET expires_at = now() - interval '1 minute'")
        .execute(&app.db)
        .await
        .unwrap();
    let (status, _) = app.get(&token, "/v1/me").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn apple_sign_in_creates_then_reuses_the_user() {
    let app = TestApp::start().await;
    let identity = app.apple.token(apple_claims("apple-sub-1", 600));
    let sign_in = |token: String| {
        let app = &app;
        async move {
            app.request(
                Method::POST,
                None,
                "/v1/auth/apple",
                Some(json!({"identity_token": token})),
            )
            .await
        }
    };
    let (status, first) = sign_in(identity.clone()).await;
    assert_eq!(status, StatusCode::OK, "{first}");
    let (status, second) = sign_in(identity).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(first["user"]["id"], second["user"]["id"]);
    let (status, _) = app.get(first["token"].as_str().unwrap(), "/v1/me").await;
    assert_eq!(status, StatusCode::OK);
}

#[tokio::test]
async fn apple_sign_in_rejects_bad_tokens() {
    let app = TestApp::start().await;
    let post = |body: serde_json::Value| {
        let app = &app;
        async move {
            app.request(Method::POST, None, "/v1/auth/apple", Some(body))
                .await
                .0
        }
    };
    let expired = app.apple.token(apple_claims("s", -3600));
    assert_eq!(
        post(json!({"identity_token": expired})).await,
        StatusCode::UNAUTHORIZED
    );

    let mut wrong_audience = apple_claims("s", 600);
    wrong_audience["aud"] = json!("com.someone.else");
    let token = app.apple.token(wrong_audience);
    assert_eq!(
        post(json!({"identity_token": token})).await,
        StatusCode::UNAUTHORIZED
    );

    let mut wrong_issuer = apple_claims("s", 600);
    wrong_issuer["iss"] = json!("https://evil.example.com");
    let token = app.apple.token(wrong_issuer);
    assert_eq!(
        post(json!({"identity_token": token})).await,
        StatusCode::UNAUTHORIZED
    );

    assert_eq!(
        post(json!({"identity_token": "garbage"})).await,
        StatusCode::UNAUTHORIZED
    );

    let good = app.apple.token(apple_claims("s", 600));
    assert_eq!(
        post(json!({"identity_token": good, "nonce": "not-the-nonce"})).await,
        StatusCode::UNAUTHORIZED
    );
}
