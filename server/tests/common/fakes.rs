use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;

use axum::extract::State;
use axum::routing::{get, post};
use axum::{Json, Router};
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use jsonwebtoken::{encode, EncodingKey, Header};
use rsa::pkcs1::EncodeRsaPrivateKey;
use rsa::traits::PublicKeyParts;
use rsa::RsaPrivateKey;
use serde_json::{json, Value};

pub const APPLE_KID: &str = "test-kid";
pub const BUNDLE_ID: &str = "com.example.sp";

pub struct AppleKeys {
    private: RsaPrivateKey,
}

impl AppleKeys {
    pub fn generate() -> Self {
        let private = RsaPrivateKey::new(&mut rand::thread_rng(), 2048).unwrap();
        Self { private }
    }

    pub fn jwks(&self) -> Value {
        let public = self.private.to_public_key();
        json!({"keys": [{
            "kty": "RSA", "kid": APPLE_KID, "use": "sig", "alg": "RS256",
            "n": URL_SAFE_NO_PAD.encode(public.n().to_bytes_be()),
            "e": URL_SAFE_NO_PAD.encode(public.e().to_bytes_be()),
        }]})
    }

    pub fn token(&self, claims: Value) -> String {
        let mut header = Header::new(jsonwebtoken::Algorithm::RS256);
        header.kid = Some(APPLE_KID.to_string());
        let der = self.private.to_pkcs1_der().unwrap();
        encode(&header, &claims, &EncodingKey::from_rsa_der(der.as_bytes())).unwrap()
    }
}

pub fn jwks_router(jwks: Value) -> Router {
    Router::new().route("/keys", get(move || async move { Json(jwks.clone()) }))
}

#[derive(Clone, Default)]
pub struct LabelApi {
    pub delay_ms: Arc<AtomicU64>,
    pub in_flight: Arc<AtomicUsize>,
    pub max_in_flight: Arc<AtomicUsize>,
    pub calls: Arc<AtomicUsize>,
}

async fn chat_completions(State(api): State<LabelApi>) -> Json<Value> {
    api.calls.fetch_add(1, Ordering::SeqCst);
    let now = api.in_flight.fetch_add(1, Ordering::SeqCst) + 1;
    api.max_in_flight.fetch_max(now, Ordering::SeqCst);
    tokio::time::sleep(Duration::from_millis(api.delay_ms.load(Ordering::SeqCst))).await;
    api.in_flight.fetch_sub(1, Ordering::SeqCst);
    Json(
        json!({"choices": [{"message": {"content": "{\"category\":\"toilet\",\"confidence\":0.9}"}}]}),
    )
}

impl LabelApi {
    pub fn router(&self) -> Router {
        Router::new()
            .route("/chat/completions", post(chat_completions))
            .with_state(self.clone())
    }
}
