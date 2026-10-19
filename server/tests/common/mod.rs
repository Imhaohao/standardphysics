#![allow(dead_code)]

pub mod fake_s3;
pub mod fakes;

use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::OnceLock;
use std::time::Duration;

use axum::Router;
use fake_s3::FakeS3;
use fakes::{AppleKeys, LabelApi, BUNDLE_ID};
use reqwest::StatusCode;
use serde_json::{json, Value};
use sp_server::config::Config;
use sp_server::state::AppState;
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use tokio::net::TcpListener;
use uuid::Uuid;

const DEFAULT_ADMIN_URL: &str = "postgres://postgres@localhost:55432/postgres";

pub struct TestOptions {
    pub label_deadline_ms: u64,
    pub label_concurrency: usize,
    pub label_key: Option<&'static str>,
}

impl Default for TestOptions {
    fn default() -> Self {
        Self {
            label_deadline_ms: 5_000,
            label_concurrency: 4,
            label_key: Some("test-key"),
        }
    }
}

pub struct TestApp {
    pub base: String,
    pub state: AppState,
    pub db: PgPool,
    pub s3: FakeS3,
    pub s3_base: String,
    pub label_api: LabelApi,
    pub apple: &'static AppleKeys,
    pub http: reqwest::Client,
}

pub fn apple_keys() -> &'static AppleKeys {
    static KEYS: OnceLock<AppleKeys> = OnceLock::new();
    KEYS.get_or_init(AppleKeys::generate)
}

async fn serve(router: Router) -> SocketAddr {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    addr
}

async fn fresh_database() -> String {
    let admin_url =
        std::env::var("TEST_DATABASE_URL").unwrap_or_else(|_| DEFAULT_ADMIN_URL.to_string());
    let admin = PgPoolOptions::new()
        .max_connections(1)
        .connect(&admin_url)
        .await
        .unwrap();
    let name = format!("sp_test_{}", Uuid::new_v4().simple());
    sqlx::query(&format!("CREATE DATABASE {name}"))
        .execute(&admin)
        .await
        .unwrap();
    let (prefix, _) = admin_url.rsplit_once('/').unwrap();
    format!("{prefix}/{name}")
}

fn test_config(
    database_url: String,
    s3_base: &str,
    jwks_url: &str,
    label_base: &str,
    opts: &TestOptions,
) -> Config {
    let mut env: HashMap<&str, String> = HashMap::from([
        ("DATABASE_URL", database_url),
        ("DB_MAX_CONNECTIONS", "5".to_string()),
        ("S3_ENDPOINT", s3_base.to_string()),
        ("S3_BUCKET", "sp-test".to_string()),
        ("S3_ACCESS_KEY_ID", "test".to_string()),
        ("S3_SECRET_ACCESS_KEY", "test".to_string()),
        ("APPLE_BUNDLE_ID", BUNDLE_ID.to_string()),
        ("APPLE_JWKS_URL", jwks_url.to_string()),
        ("LABEL_API_BASE", label_base.to_string()),
        ("LABEL_MODEL", "test-model".to_string()),
        ("LABEL_DEADLINE_MS", opts.label_deadline_ms.to_string()),
        ("LABEL_CONCURRENCY", opts.label_concurrency.to_string()),
        ("RUN_JOB_WORKER", "false".to_string()),
    ]);
    if let Some(key) = opts.label_key {
        env.insert("LABEL_API_KEY", key.to_string());
    }
    Config::from_lookup(|k| env.get(k).cloned()).unwrap()
}

impl TestApp {
    pub async fn start() -> Self {
        Self::start_with(TestOptions::default()).await
    }

    pub async fn start_with(opts: TestOptions) -> Self {
        let s3 = FakeS3::default();
        let s3_addr = serve(s3.router()).await;
        let label_api = LabelApi::default();
        let label_addr = serve(label_api.router()).await;
        let apple = apple_keys();
        let jwks_addr = serve(fakes::jwks_router(apple.jwks())).await;

        let s3_base = format!("http://{s3_addr}");
        let cfg = test_config(
            fresh_database().await,
            &s3_base,
            &format!("http://{jwks_addr}/keys"),
            &format!("http://{label_addr}"),
            &opts,
        );
        let state = AppState::connect(cfg).await.unwrap();
        let db = state.db.clone();
        let addr = serve(sp_server::build_router(state.clone())).await;
        Self {
            base: format!("http://{addr}"),
            state,
            db,
            s3,
            s3_base,
            label_api,
            apple,
            http: reqwest::Client::new(),
        }
    }

    pub fn url(&self, path: &str) -> String {
        format!("{}{path}", self.base)
    }

    pub fn ws_url(&self, path: &str) -> String {
        format!("ws{}{path}", &self.base["http".len()..])
    }

    pub async fn request(
        &self,
        method: reqwest::Method,
        token: Option<&str>,
        path: &str,
        body: Option<Value>,
    ) -> (StatusCode, Value) {
        let mut req = self.http.request(method, self.url(path));
        if let Some(token) = token {
            req = req.bearer_auth(token);
        }
        if let Some(body) = body {
            req = req.json(&body);
        }
        let resp = req.send().await.unwrap();
        let status = resp.status();
        let bytes = resp.bytes().await.unwrap();
        (
            status,
            serde_json::from_slice(&bytes).unwrap_or(Value::Null),
        )
    }

    pub async fn post(&self, token: &str, path: &str, body: Value) -> (StatusCode, Value) {
        self.request(reqwest::Method::POST, Some(token), path, Some(body))
            .await
    }

    pub async fn get(&self, token: &str, path: &str) -> (StatusCode, Value) {
        self.request(reqwest::Method::GET, Some(token), path, None)
            .await
    }

    pub async fn register(&self, email: &str) -> String {
        let (status, body) = self
            .request(
                reqwest::Method::POST,
                None,
                "/v1/auth/register",
                Some(json!({"email": email, "password": "correct horse battery"})),
            )
            .await;
        assert_eq!(status, StatusCode::CREATED, "{body}");
        body["token"].as_str().unwrap().to_string()
    }

    pub async fn create_scan(&self, token: &str) -> String {
        let (status, body) = self
            .post(token, "/v1/scans", json!({"name": "Test shop"}))
            .await;
        assert_eq!(status, StatusCode::CREATED, "{body}");
        body["id"].as_str().unwrap().to_string()
    }
}

pub async fn wait_until<F, Fut>(what: &str, mut check: F)
where
    F: FnMut() -> Fut,
    Fut: std::future::Future<Output = bool>,
{
    for _ in 0..100 {
        if check().await {
            return;
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    panic!("timed out waiting for {what}");
}

fn wall_json(id: &str, length: f64, transform: [f64; 16]) -> Value {
    json!({"identifier": id, "dimensions": [length, 2.5, 0.1], "transform": transform})
}

pub fn door_id(room_id: &str) -> String {
    format!("{room_id}-door")
}

/// A 4 x 3 m RoomPlan CapturedRoom with one door on the north wall. Rooms are placed on a
/// 6 m grid by `slot` so a multi-room scan does not overlap itself.
pub fn door_room_at(room_id: &str, door_width: f64, slot: usize) -> Value {
    let ox = 6.0 * slot as f64;
    let wall = |name: &str, length: f64, rot: bool, x: f64, z: f64| {
        let t = if rot {
            [
                0.,
                0.,
                -1.,
                0.,
                0.,
                1.,
                0.,
                0.,
                1.,
                0.,
                0.,
                0.,
                ox + x,
                1.25,
                z,
                1.,
            ]
        } else {
            [
                1.,
                0.,
                0.,
                0.,
                0.,
                1.,
                0.,
                0.,
                0.,
                0.,
                1.,
                0.,
                ox + x,
                1.25,
                z,
                1.,
            ]
        };
        wall_json(&format!("{room_id}-{name}"), length, t)
    };
    json!({
        "identifier": room_id,
        "story": 0,
        "walls": [
            wall("n", 4.0, false, 0.0, -1.5),
            wall("s", 4.0, false, 0.0, 1.5),
            wall("e", 3.0, true, 2.0, 0.0),
            wall("w", 3.0, true, -2.0, 0.0),
        ],
        "doors": [{
            "identifier": door_id(room_id),
            "parentIdentifier": format!("{room_id}-n"),
            "category": {"door": {"isOpen": false}},
            "dimensions": [door_width, 2.03, 0.0],
            "transform": [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., ox, 1.015, -1.5, 1.],
        }],
    })
}

pub fn door_room(room_id: &str, door_width: f64) -> Value {
    door_room_at(room_id, door_width, 0)
}

pub fn findings_for<'a>(findings: &'a Value, subject: &str) -> Vec<&'a Value> {
    findings
        .as_array()
        .unwrap()
        .iter()
        .filter(|f| f["subject_id"] == subject)
        .collect()
}

pub fn sha256_hex(data: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    hex::encode(Sha256::digest(data))
}

pub async fn upload_artifact(
    app: &TestApp,
    token: &str,
    scan_id: &str,
    kind: &str,
    data: &[u8],
) -> String {
    let body = json!({
        "kind": kind, "filename": format!("{kind}.bin"), "content_type": "image/jpeg",
        "size_bytes": data.len(),
    });
    let base = format!("/v1/scans/{scan_id}/uploads");
    let (status, upload) = app.post(token, &base, body).await;
    assert_eq!(status, StatusCode::CREATED, "{upload}");
    let upload_id = upload["id"].as_str().unwrap();
    let (_, presigned) = app
        .post(
            token,
            &format!("{base}/{upload_id}/parts"),
            json!({"part_numbers": [1]}),
        )
        .await;
    let url = presigned["parts"][0]["url"].as_str().unwrap();
    let resp = app.http.put(url).body(data.to_vec()).send().await.unwrap();
    assert!(resp.status().is_success());
    let (status, artifact) = app
        .post(
            token,
            &format!("{base}/{upload_id}/complete"),
            json!({"sha256": sha256_hex(data)}),
        )
        .await;
    assert_eq!(status, StatusCode::OK, "{artifact}");
    artifact["id"].as_str().unwrap().to_string()
}

pub type WsStream =
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

pub async fn connect_live(app: &TestApp, token: &str, scan_id: &str, role: &str) -> WsStream {
    let url = app.ws_url(&format!(
        "/v1/scans/{scan_id}/live?token={token}&role={role}"
    ));
    let (socket, _) = tokio_tungstenite::connect_async(url).await.unwrap();
    socket
}

pub async fn send_json(socket: &mut WsStream, value: Value) {
    use futures::SinkExt;
    socket
        .send(tokio_tungstenite::tungstenite::Message::Text(
            value.to_string().into(),
        ))
        .await
        .unwrap();
}

pub async fn next_json(socket: &mut WsStream) -> Value {
    use futures::StreamExt;
    loop {
        let message = tokio::time::timeout(Duration::from_secs(5), socket.next())
            .await
            .expect("timed out waiting for websocket message")
            .expect("socket closed")
            .unwrap();
        if let tokio_tungstenite::tungstenite::Message::Text(text) = message {
            return serde_json::from_str(text.as_str()).unwrap();
        }
    }
}

pub async fn next_of_type(socket: &mut WsStream, kind: &str) -> Value {
    loop {
        let message = next_json(socket).await;
        if message["type"] == kind {
            return message;
        }
    }
}
