use axum::extract::State;
use axum::http::StatusCode;
use axum::Json;
use serde::Serialize;
use utoipa::ToSchema;

use crate::state::AppState;

#[derive(Serialize, ToSchema)]
pub struct Health {
    pub status: String,
    pub version: String,
}

#[derive(Serialize, ToSchema)]
pub struct Readiness {
    pub database: bool,
    pub storage: bool,
}

#[utoipa::path(get, path = "/health", tag = "ops", responses((status = 200, body = Health)))]
pub async fn health() -> Json<Health> {
    Json(Health {
        status: "ok".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
    })
}

#[utoipa::path(
    get, path = "/health/ready", tag = "ops",
    responses((status = 200, body = Readiness), (status = 503, body = Readiness))
)]
pub async fn ready(State(state): State<AppState>) -> (StatusCode, Json<Readiness>) {
    let database = sqlx::query("SELECT 1").execute(&state.db).await.is_ok();
    let storage = state.storage.check_bucket().await.is_ok();
    let code = if database && storage {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };
    (code, Json(Readiness { database, storage }))
}
