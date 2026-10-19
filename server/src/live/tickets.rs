use anyhow::Result;
use axum::extract::{Path, State};
use axum::Json;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use rand::RngCore;
use serde::Serialize;
use sqlx::PgPool;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::auth::session::hash_token;
use crate::auth::AuthUser;
use crate::error::{ApiResult, ErrorBody};
use crate::scans::repo::get_owned_scan;
use crate::state::AppState;

pub const TICKET_TTL_SECS: i64 = 30;

#[derive(Serialize, ToSchema)]
pub struct LiveTicket {
    /// Pass as `?ticket=` when opening the WebSocket. Single use, valid for `expires_in_secs`.
    pub ticket: String,
    pub expires_in_secs: i64,
}

fn generate_ticket() -> String {
    let mut bytes = [0u8; 24];
    rand::thread_rng().fill_bytes(&mut bytes);
    format!("spt_{}", URL_SAFE_NO_PAD.encode(bytes))
}

pub async fn issue_ticket(db: &PgPool, user_id: Uuid, scan_id: Uuid) -> Result<String> {
    sqlx::query("DELETE FROM live_tickets WHERE expires_at < now()")
        .execute(db)
        .await?;
    let ticket = generate_ticket();
    sqlx::query(
        "INSERT INTO live_tickets (ticket_hash, user_id, scan_id, expires_at)
         VALUES ($1, $2, $3, now() + make_interval(secs => $4))",
    )
    .bind(hash_token(&ticket))
    .bind(user_id)
    .bind(scan_id)
    .bind(TICKET_TTL_SECS as f64)
    .execute(db)
    .await?;
    Ok(ticket)
}

pub async fn consume_ticket(db: &PgPool, ticket: &str, scan_id: Uuid) -> Result<Option<Uuid>> {
    let row: Option<(Uuid,)> = sqlx::query_as(
        "DELETE FROM live_tickets
         WHERE ticket_hash = $1 AND scan_id = $2 AND expires_at > now()
         RETURNING user_id",
    )
    .bind(hash_token(ticket))
    .bind(scan_id)
    .fetch_optional(db)
    .await?;
    Ok(row.map(|(user_id,)| user_id))
}

#[utoipa::path(
    post, path = "/v1/scans/{scan_id}/live-ticket", tag = "live",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    responses((status = 200, body = LiveTicket), (status = 404, body = ErrorBody))
)]
pub async fn create_live_ticket(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
) -> ApiResult<Json<LiveTicket>> {
    get_owned_scan(&state.db, user_id, scan_id).await?;
    let ticket = issue_ticket(&state.db, user_id, scan_id).await?;
    Ok(Json(LiveTicket {
        ticket,
        expires_in_secs: TICKET_TTL_SECS,
    }))
}
