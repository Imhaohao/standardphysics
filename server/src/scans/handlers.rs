use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Json;
use uuid::Uuid;

use super::models::{CreateScan, Report, Scan};
use super::repo;
use crate::assessments;
use crate::auth::AuthUser;
use crate::error::{ApiError, ApiResult, ErrorBody};
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
    request_body = CreateScan,
    responses((status = 201, body = Scan), (status = 401, body = ErrorBody))
)]
pub async fn create_scan(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Json(body): Json<CreateScan>,
) -> ApiResult<(StatusCode, Json<Scan>)> {
    let name =
        clean_text(body.name, MAX_NAME_LEN)?.unwrap_or_else(|| DEFAULT_SCAN_NAME.to_string());
    let site = clean_text(body.site_name, MAX_NAME_LEN)?;
    let scan = repo::insert_scan(&state.db, user_id, &name, site.as_deref()).await?;
    Ok((StatusCode::CREATED, Json(scan)))
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
