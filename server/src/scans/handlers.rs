use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::Response;
use axum::Json;
use uuid::Uuid;

use super::models::{CreateScan, Report, Scan, UpdateScan};
use super::repo;
use crate::assessments;
use crate::auth::AuthUser;
use crate::error::{ApiError, ApiResult, ErrorBody};
use crate::idempotency;
use crate::state::AppState;

const DEFAULT_SCAN_NAME: &str = "Untitled scan";
const MAX_NAME_LEN: usize = 200;

fn clean_text(raw: Option<String>, max: usize) -> ApiResult<Option<String>> {
    let Some(text) = raw.map(|t| t.trim().to_string()).filter(|t| !t.is_empty()) else {
        return Ok(None);
    };
    if text.chars().count() > max {
        return Err(ApiError::bad_request(format!(
            "text is longer than {max} characters"
        )));
    }
    Ok(Some(text))
}

#[utoipa::path(
    post, path = "/v1/scans", tag = "scans",
    security(("bearer" = [])),
    params(("Idempotency-Key" = Option<String>, Header, description = "Repeats with the same key and body within 24 h replay the first response; a different body is 409.")),
    request_body = CreateScan,
    responses((status = 201, body = Scan), (status = 401, body = ErrorBody), (status = 409, body = ErrorBody))
)]
pub async fn create_scan(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    headers: HeaderMap,
    Json(body): Json<CreateScan>,
) -> ApiResult<Response> {
    idempotency::run(
        &state.db,
        user_id,
        "POST /v1/scans",
        &headers,
        &body,
        || insert_new_scan(&state, user_id, &body),
    )
    .await
}

async fn insert_new_scan(
    state: &AppState,
    user_id: Uuid,
    body: &CreateScan,
) -> ApiResult<(StatusCode, serde_json::Value)> {
    let name = clean_text(body.name.clone(), MAX_NAME_LEN)?
        .unwrap_or_else(|| DEFAULT_SCAN_NAME.to_string());
    let site = clean_text(body.site_name.clone(), MAX_NAME_LEN)?;
    let scan = repo::insert_scan(&state.db, user_id, &name, site.as_deref()).await?;
    let value = serde_json::to_value(scan).map_err(|e| ApiError::Internal(e.into()))?;
    Ok((StatusCode::CREATED, value))
}

#[utoipa::path(
    get, path = "/v1/scans", tag = "scans",
    security(("bearer" = [])),
    responses((status = 200, body = Vec<Scan>), (status = 401, body = ErrorBody))
)]
pub async fn list_scans(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
) -> ApiResult<Json<Vec<Scan>>> {
    Ok(Json(repo::list_scans(&state.db, user_id).await?))
}

#[utoipa::path(
    get, path = "/v1/scans/{scan_id}", tag = "scans",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    responses((status = 200, body = Scan), (status = 404, body = ErrorBody))
)]
pub async fn get_scan(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
) -> ApiResult<Json<Scan>> {
    Ok(Json(
        repo::get_owned_scan(&state.db, user_id, scan_id).await?,
    ))
}

#[utoipa::path(
    get, path = "/v1/scans/{scan_id}/assessment", tag = "scans",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    responses((status = 200, body = Report), (status = 404, body = ErrorBody))
)]
pub async fn get_assessment(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
) -> ApiResult<Json<Report>> {
    repo::get_owned_scan(&state.db, user_id, scan_id).await?;
    let report = assessments::latest_report(&state.db, scan_id)
        .await?
        .ok_or(ApiError::NotFound)?;
    Ok(Json(report))
}

#[utoipa::path(
    get, path = "/v1/scans/{scan_id}/scene", tag = "scans",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    responses(
        (status = 200, description = "Merged sp-core Scene JSON (rooms, connections, observations)", body = Object),
        (status = 404, body = ErrorBody, description = "Not your scan, or no room has been captured yet"),
    )
)]
pub async fn get_scene(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
) -> ApiResult<Json<serde_json::Value>> {
    repo::get_owned_scan(&state.db, user_id, scan_id).await?;
    let scene = crate::finish::pipeline::merged_scene(&state.db, scan_id)
        .await?
        .ok_or(ApiError::NotFound)?;
    Ok(Json(scene))
}

#[utoipa::path(
    patch, path = "/v1/scans/{scan_id}", tag = "scans",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    request_body = UpdateScan,
    responses((status = 200, body = Scan), (status = 400, body = ErrorBody), (status = 404, body = ErrorBody))
)]
pub async fn update_scan(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
    Json(body): Json<UpdateScan>,
) -> ApiResult<Json<Scan>> {
    repo::get_owned_scan(&state.db, user_id, scan_id).await?;
    let name = match body.name {
        Some(raw) => Some(
            clean_text(Some(raw), MAX_NAME_LEN)?
                .ok_or_else(|| ApiError::bad_request("name cannot be empty"))?,
        ),
        None => None,
    };
    let site = body
        .site_name
        .map(|raw| clean_text(raw, MAX_NAME_LEN))
        .transpose()?;
    let scan = repo::rename_scan(
        &state.db,
        scan_id,
        name.as_deref(),
        site.as_ref().map(Option::as_deref),
    )
    .await?;
    Ok(Json(scan))
}

#[utoipa::path(
    delete, path = "/v1/scans/{scan_id}", tag = "scans",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    responses((status = 204, description = "The scan, its report, answers, share links and uploaded files are gone"), (status = 404, body = ErrorBody))
)]
pub async fn delete_scan(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
) -> ApiResult<StatusCode> {
    repo::get_owned_scan(&state.db, user_id, scan_id).await?;
    crate::purge::delete_scan(&state.db, &state.storage, scan_id).await?;
    Ok(StatusCode::NO_CONTENT)
}
