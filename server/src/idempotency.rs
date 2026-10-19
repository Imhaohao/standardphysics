use std::future::Future;

use axum::http::{HeaderMap, HeaderName, HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use sqlx::PgPool;
use uuid::Uuid;

use crate::error::{ApiError, ApiResult};

pub const KEY_HEADER: &str = "idempotency-key";
pub const REPLAYED_HEADER: &str = "idempotent-replayed";
pub const RETENTION_HOURS: i32 = 24;
/// A key still marked in progress after this long belongs to a request that died before it could
/// record or release it (a crash or a dropped connection); a retry takes it over.
pub const STALE_IN_PROGRESS_SECS: i32 = 120;
const MAX_KEY_LEN: usize = 255;

enum Begin {
    Fresh,
    Replay(StatusCode, Value),
}

fn key_from_headers(headers: &HeaderMap) -> ApiResult<Option<String>> {
    let Some(raw) = headers.get(KEY_HEADER) else {
        return Ok(None);
    };
    let key = raw
        .to_str()
        .map_err(|_| ApiError::bad_request("Idempotency-Key must be visible ASCII"))?
        .trim();
    if key.is_empty() || key.len() > MAX_KEY_LEN {
        return Err(ApiError::bad_request(
            "Idempotency-Key must be 1 to 255 characters",
        ));
    }
    Ok(Some(key.to_string()))
}

fn request_hash<T: Serialize>(body: &T) -> ApiResult<String> {
    let bytes = serde_json::to_vec(body).map_err(|e| ApiError::Internal(e.into()))?;
    Ok(hex::encode(Sha256::digest(bytes)))
}

async fn begin(db: &PgPool, user_id: Uuid, scope: &str, key: &str, hash: &str) -> ApiResult<Begin> {
    sqlx::query(
        "DELETE FROM idempotency_keys
         WHERE user_id = $1 AND scope = $2 AND key = $3
           AND (created_at < now() - make_interval(hours => $4)
                OR (status IS NULL AND created_at < now() - make_interval(secs => $5)))",
    )
    .bind(user_id)
    .bind(scope)
    .bind(key)
    .bind(RETENTION_HOURS)
    .bind(f64::from(STALE_IN_PROGRESS_SECS))
    .execute(db)
    .await?;
    let inserted = sqlx::query(
        "INSERT INTO idempotency_keys (user_id, scope, key, request_hash)
         VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
    )
    .bind(user_id)
    .bind(scope)
    .bind(key)
    .bind(hash)
    .execute(db)
    .await?;
    if inserted.rows_affected() == 1 {
        return Ok(Begin::Fresh);
    }
    existing_outcome(db, user_id, scope, key, hash).await
}

async fn existing_outcome(
    db: &PgPool,
    user_id: Uuid,
    scope: &str,
    key: &str,
    hash: &str,
) -> ApiResult<Begin> {
    let row: Option<(String, Option<i32>, Option<Value>)> = sqlx::query_as(
        "SELECT request_hash, status, response FROM idempotency_keys
         WHERE user_id = $1 AND scope = $2 AND key = $3",
    )
    .bind(user_id)
    .bind(scope)
    .bind(key)
    .fetch_optional(db)
    .await?;
    let Some((stored_hash, status, response)) = row else {
        return Err(ApiError::Conflict(
            "Idempotency-Key was just released, retry".into(),
        ));
    };
    if stored_hash != hash {
        return Err(ApiError::Conflict(
            "Idempotency-Key was already used with a different request".into(),
        ));
    }
    match (status, response) {
        (Some(status), Some(response)) => {
            let code = StatusCode::from_u16(status as u16).unwrap_or(StatusCode::OK);
            Ok(Begin::Replay(code, response))
        }
        _ => Err(ApiError::Conflict(
            "a request with this Idempotency-Key is still in progress".into(),
        )),
    }
}

async fn record(
    db: &PgPool,
    user_id: Uuid,
    scope: &str,
    key: &str,
    status: StatusCode,
    body: &Value,
) -> ApiResult<()> {
    sqlx::query(
        "UPDATE idempotency_keys SET status = $4, response = $5
         WHERE user_id = $1 AND scope = $2 AND key = $3",
    )
    .bind(user_id)
    .bind(scope)
    .bind(key)
    .bind(status.as_u16() as i32)
    .bind(body)
    .execute(db)
    .await?;
    Ok(())
}

async fn release(db: &PgPool, user_id: Uuid, scope: &str, key: &str) {
    let result =
        sqlx::query("DELETE FROM idempotency_keys WHERE user_id = $1 AND scope = $2 AND key = $3")
            .bind(user_id)
            .bind(scope)
            .bind(key)
            .execute(db)
            .await;
    if let Err(err) = result {
        tracing::warn!(error = %err, "could not release idempotency key");
    }
}

fn respond(status: StatusCode, body: Value, replayed: bool) -> Response {
    let mut response = (status, Json(body)).into_response();
    if replayed {
        response.headers_mut().insert(
            HeaderName::from_static(REPLAYED_HEADER),
            HeaderValue::from_static("true"),
        );
    }
    response
}

/// Runs `action` once per (user, scope, Idempotency-Key). A repeat with the same body within 24 h
/// replays the stored response; the same key with a different body is a 409.
pub async fn run<T, F, Fut>(
    db: &PgPool,
    user_id: Uuid,
    scope: &str,
    headers: &HeaderMap,
    request: &T,
    action: F,
) -> ApiResult<Response>
where
    T: Serialize,
    F: FnOnce() -> Fut,
    Fut: Future<Output = ApiResult<(StatusCode, Value)>>,
{
    let Some(key) = key_from_headers(headers)? else {
        let (status, body) = action().await?;
        return Ok(respond(status, body, false));
    };
    let hash = request_hash(request)?;
    if let Begin::Replay(status, body) = begin(db, user_id, scope, &key, &hash).await? {
        return Ok(respond(status, body, true));
    }
    match action().await {
        Ok((status, body)) => {
            record(db, user_id, scope, &key, status, &body).await?;
            Ok(respond(status, body, false))
        }
        Err(err) => {
            release(db, user_id, scope, &key).await;
            Err(err)
        }
    }
}
