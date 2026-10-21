//! Read-only report links. Anyone holding the token can read the report and scene, nothing else.

use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Json;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use chrono::{DateTime, Utc};
use rand::RngCore;
use serde::Serialize;
use sqlx::PgPool;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::assessments;
use crate::auth::AuthUser;
use crate::error::{ApiError, ApiResult, ErrorBody};
use crate::finish::pipeline::merged_scene;
use crate::scans::models::{Report, Scan};
use crate::scans::repo::{get_owned_scan, get_scan_by_id};
use crate::state::AppState;

const TOKEN_BYTES: usize = 32;
const MAX_TOKEN_LEN: usize = 64;

#[derive(Clone, Debug, Serialize, ToSchema, sqlx::FromRow)]
pub struct Share {
    /// Put this in the web link: `/r/{token}`.
    pub token: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Serialize, ToSchema)]
pub struct SharedReport {
    pub scan: Scan,
    pub report: Report,
    /// Merged sp-core Scene, or null when no room was captured.
    #[schema(value_type = Option<Object>)]
    pub scene: Option<serde_json::Value>,
}

fn new_token() -> String {
    let mut bytes = [0u8; TOKEN_BYTES];
    rand::thread_rng().fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(bytes)
}

async fn shared_scan_id(db: &PgPool, token: &str) -> ApiResult<Uuid> {
    if token.len() > MAX_TOKEN_LEN {
        return Err(ApiError::NotFound);
    }
    let row: Option<(Uuid,)> = sqlx::query_as("SELECT scan_id FROM scan_shares WHERE token = $1")
        .bind(token)
        .fetch_optional(db)
        .await?;
    row.map(|(id,)| id).ok_or(ApiError::NotFound)
}

#[utoipa::path(
    post, path = "/v1/scans/{scan_id}/shares", tag = "shares",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    responses((status = 201, body = Share), (status = 404, body = ErrorBody))
)]
pub async fn create_share(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
) -> ApiResult<(StatusCode, Json<Share>)> {
    get_owned_scan(&state.db, user_id, scan_id).await?;
    let share: Share = sqlx::query_as(
        "INSERT INTO scan_shares (token, scan_id) VALUES ($1, $2) RETURNING token, created_at",
    )
    .bind(new_token())
    .bind(scan_id)
    .fetch_one(&state.db)
    .await?;
    Ok((StatusCode::CREATED, Json(share)))
}

#[utoipa::path(
    get, path = "/v1/scans/{scan_id}/shares", tag = "shares",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    responses((status = 200, body = Vec<Share>), (status = 404, body = ErrorBody))
)]
pub async fn list_shares(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
) -> ApiResult<Json<Vec<Share>>> {
    get_owned_scan(&state.db, user_id, scan_id).await?;
    let shares = sqlx::query_as(
        "SELECT token, created_at FROM scan_shares WHERE scan_id = $1 ORDER BY created_at DESC",
    )
    .bind(scan_id)
    .fetch_all(&state.db)
    .await?;
    Ok(Json(shares))
}

#[utoipa::path(
    delete, path = "/v1/scans/{scan_id}/shares/{token}", tag = "shares",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path), ("token" = String, Path)),
    responses((status = 204), (status = 404, body = ErrorBody))
)]
pub async fn delete_share(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path((scan_id, token)): Path<(Uuid, String)>,
) -> ApiResult<StatusCode> {
    get_owned_scan(&state.db, user_id, scan_id).await?;
    let deleted = sqlx::query("DELETE FROM scan_shares WHERE token = $1 AND scan_id = $2")
        .bind(&token)
        .bind(scan_id)
        .execute(&state.db)
        .await?;
    if deleted.rows_affected() == 0 {
        return Err(ApiError::NotFound);
    }
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(
    get, path = "/v1/shared/{token}", tag = "shares",
    params(("token" = String, Path)),
    responses(
        (status = 200, body = SharedReport),
        (status = 404, body = ErrorBody, description = "Unknown or revoked link, or the scan has no report yet"),
    )
)]
pub async fn get_shared_report(
    State(state): State<AppState>,
    Path(token): Path<String>,
) -> ApiResult<Json<SharedReport>> {
    let scan_id = shared_scan_id(&state.db, &token).await?;
    let scan = get_scan_by_id(&state.db, scan_id).await?;
    let report = assessments::latest_report(&state.db, scan_id)
        .await?
        .ok_or(ApiError::NotFound)?;
    let scene = merged_scene(&state.db, scan_id).await?;
    Ok(Json(SharedReport {
        scan,
        report,
        scene,
    }))
}
