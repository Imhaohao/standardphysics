use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::Response;
use axum::Json;
use uuid::Uuid;

use super::models::{
    Artifact, CompleteUpload, CreateUpload, PresignRequest, PresignResponse, Upload, UploadRecord,
    UploadStatus,
};
use super::plan::{plan_parts, safe_filename, valid_kind, valid_sha256, validate_part_numbers};
use super::repo;
use super::room_artifact::{apply_room_upload, is_room, require_scan_capturing};
use crate::auth::AuthUser;
use crate::error::{ApiError, ApiResult, ErrorBody};
use crate::idempotency;
use crate::scans::repo::get_owned_scan;
use crate::state::AppState;
use crate::storage::UploadedPart;

fn storage_error(err: anyhow::Error) -> ApiError {
    ApiError::Storage(format!("{err:#}"))
}

fn object_key(scan_id: Uuid, upload_id: Uuid, kind: &str, filename: &str) -> String {
    format!(
        "scans/{scan_id}/{kind}/{upload_id}/{}",
        safe_filename(filename)
    )
}

fn validate_create(body: &CreateUpload) -> ApiResult<()> {
    if !valid_kind(&body.kind) {
        return Err(ApiError::bad_request(
            "kind must be 1-32 chars of a-z, 0-9, _ or -",
        ));
    }
    if body.filename.trim().is_empty() || body.content_type.trim().is_empty() {
        return Err(ApiError::bad_request(
            "filename and content_type are required",
        ));
    }
    Ok(())
}

async fn open_upload(
    state: &AppState,
    user_id: Uuid,
    scan_id: Uuid,
    upload_id: Uuid,
) -> ApiResult<UploadRecord> {
    get_owned_scan(&state.db, user_id, scan_id).await?;
    repo::get_upload(&state.db, scan_id, upload_id).await
}

fn require_open(upload: &UploadRecord) -> ApiResult<()> {
    if upload.state == "open" {
        return Ok(());
    }
    Err(ApiError::Conflict(format!("upload is {}", upload.state)))
}

#[utoipa::path(
    post, path = "/v1/scans/{scan_id}/uploads", tag = "uploads",
    security(("bearer" = [])),
    params(
        ("scan_id" = Uuid, Path),
        ("Idempotency-Key" = Option<String>, Header, description = "Repeats with the same key and body within 24 h replay the first response; a different body is 409."),
    ),
    request_body = CreateUpload,
    responses((status = 201, body = Upload), (status = 404, body = ErrorBody), (status = 409, body = ErrorBody))
)]
pub async fn create_upload(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
    headers: HeaderMap,
    Json(body): Json<CreateUpload>,
) -> ApiResult<Response> {
    get_owned_scan(&state.db, user_id, scan_id).await?;
    let scope = format!("POST /v1/scans/{scan_id}/uploads");
    idempotency::run(&state.db, user_id, &scope, &headers, &body, || {
        start_upload(&state, scan_id, body.clone())
    })
    .await
}

async fn start_upload(
    state: &AppState,
    scan_id: Uuid,
    body: CreateUpload,
) -> ApiResult<(StatusCode, serde_json::Value)> {
    validate_create(&body)?;
    let plan = plan_parts(body.size_bytes, body.part_size)?;
    let id = Uuid::new_v4();
    let key = object_key(scan_id, id, &body.kind, &body.filename);
    let s3_upload_id = state
        .storage
        .create_multipart(&key, &body.content_type)
        .await
        .map_err(storage_error)?;
    let record = UploadRecord {
        id,
        scan_id,
        kind: body.kind,
        filename: body.filename,
        content_type: body.content_type,
        size_bytes: body.size_bytes,
        part_size: plan.part_size,
        part_count: plan.part_count,
        s3_key: key,
        s3_upload_id,
        state: "open".to_string(),
        created_at: chrono::Utc::now(),
    };
    repo::insert_upload(&state.db, &record).await?;
    let value = serde_json::to_value(record.public()).map_err(|e| ApiError::Internal(e.into()))?;
    Ok((StatusCode::CREATED, value))
}

#[utoipa::path(
    get, path = "/v1/scans/{scan_id}/uploads/{upload_id}", tag = "uploads",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path), ("upload_id" = Uuid, Path)),
    responses((status = 200, body = UploadStatus), (status = 404, body = ErrorBody))
)]
pub async fn upload_status(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path((scan_id, upload_id)): Path<(Uuid, Uuid)>,
) -> ApiResult<Json<UploadStatus>> {
    let upload = open_upload(&state, user_id, scan_id, upload_id).await?;
    let uploaded_parts = if upload.state == "open" {
        state
            .storage
            .list_parts(&upload.s3_key, &upload.s3_upload_id)
            .await
            .map_err(storage_error)?
    } else {
        Vec::new()
    };
    Ok(Json(UploadStatus {
        upload: upload.public(),
        uploaded_parts,
    }))
}

#[utoipa::path(
    post, path = "/v1/scans/{scan_id}/uploads/{upload_id}/parts", tag = "uploads",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path), ("upload_id" = Uuid, Path)),
    request_body = PresignRequest,
    responses((status = 200, body = PresignResponse), (status = 404, body = ErrorBody))
)]
pub async fn presign_parts(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path((scan_id, upload_id)): Path<(Uuid, Uuid)>,
    Json(body): Json<PresignRequest>,
) -> ApiResult<Json<PresignResponse>> {
    let upload = open_upload(&state, user_id, scan_id, upload_id).await?;
    require_open(&upload)?;
    validate_part_numbers(&body.part_numbers, upload.part_count)?;
    let mut parts = Vec::with_capacity(body.part_numbers.len());
    for number in body.part_numbers {
        let part = state
            .storage
            .presign_part(&upload.s3_key, &upload.s3_upload_id, number)
            .await
            .map_err(storage_error)?;
        parts.push(part);
    }
    Ok(Json(PresignResponse {
        host: state.storage.public_host().map(str::to_string),
        parts,
        expires_in_secs: state.cfg.storage.presign_ttl.as_secs(),
    }))
}

fn ordered_etags(parts: &[UploadedPart], upload: &UploadRecord) -> ApiResult<Vec<(i32, String)>> {
    let mut sorted: Vec<&UploadedPart> = parts.iter().collect();
    sorted.sort_by_key(|p| p.part_number);
    let missing: Vec<i32> = (1..=upload.part_count)
        .filter(|n| !sorted.iter().any(|p| p.part_number == *n))
        .collect();
    if !missing.is_empty() {
        return Err(ApiError::Unprocessable(format!(
            "missing parts: {missing:?}"
        )));
    }
    let total: i64 = sorted.iter().map(|p| p.size_bytes).sum();
    if total != upload.size_bytes {
        return Err(ApiError::Unprocessable(format!(
            "uploaded {total} bytes but expected {}",
            upload.size_bytes
        )));
    }
    Ok(sorted
        .into_iter()
        .map(|p| (p.part_number, p.etag.clone()))
        .collect())
}

async fn discard_bad_object(state: &AppState, upload: &UploadRecord, reason: String) -> ApiError {
    if let Err(err) = state.storage.delete_object(&upload.s3_key).await {
        tracing::warn!(error = %err, key = %upload.s3_key, "could not delete rejected object");
    }
    if let Err(err) = repo::set_upload_state(&state.db, upload.id, "aborted").await {
        tracing::warn!(error = %err, "could not mark rejected upload aborted");
    }
    ApiError::Unprocessable(reason)
}

async fn verify_object(state: &AppState, upload: &UploadRecord, sha256: &str) -> ApiResult<()> {
    let size = state
        .storage
        .object_size(&upload.s3_key)
        .await
        .map_err(storage_error)?;
    if size as i64 != upload.size_bytes {
        let reason = format!(
            "stored object is {size} bytes, expected {}",
            upload.size_bytes
        );
        return Err(discard_bad_object(state, upload, reason).await);
    }
    if size > state.cfg.storage.verify_max_bytes {
        return Ok(());
    }
    let actual = state
        .storage
        .sha256_hex(&upload.s3_key)
        .await
        .map_err(storage_error)?;
    if actual != sha256 {
        let reason = "sha256 does not match the uploaded bytes".to_string();
        return Err(discard_bad_object(state, upload, reason).await);
    }
    Ok(())
}

async fn ingest_room(state: &AppState, upload: &UploadRecord) -> ApiResult<()> {
    match apply_room_upload(state, upload).await {
        Err(ApiError::Unprocessable(reason)) => {
            Err(discard_bad_object(state, upload, reason).await)
        }
        other => other,
    }
}

#[utoipa::path(
    post, path = "/v1/scans/{scan_id}/uploads/{upload_id}/complete", tag = "uploads",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path), ("upload_id" = Uuid, Path)),
    request_body = CompleteUpload,
    responses(
        (status = 200, body = Artifact),
        (status = 404, body = ErrorBody),
        (status = 409, body = ErrorBody),
        (status = 422, body = ErrorBody),
    )
)]
pub async fn complete_upload(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path((scan_id, upload_id)): Path<(Uuid, Uuid)>,
    Json(body): Json<CompleteUpload>,
) -> ApiResult<Json<Artifact>> {
    let upload = open_upload(&state, user_id, scan_id, upload_id).await?;
    if upload.state == "complete" {
        let existing = repo::artifact_for_upload(&state.db, upload.id).await?;
        return existing.map(Json).ok_or(ApiError::NotFound);
    }
    require_open(&upload)?;
    if is_room(&upload) {
        require_scan_capturing(&state, scan_id).await?;
    }
    let sha256 = body.sha256.to_lowercase();
    if !valid_sha256(&sha256) {
        return Err(ApiError::bad_request("sha256 must be 64 hex characters"));
    }
    let parts = state
        .storage
        .list_parts(&upload.s3_key, &upload.s3_upload_id)
        .await
        .map_err(storage_error)?;
    let etags = ordered_etags(&parts, &upload)?;
    state
        .storage
        .complete_multipart(&upload.s3_key, &upload.s3_upload_id, &etags)
        .await
        .map_err(storage_error)?;
    verify_object(&state, &upload, &sha256).await?;
    if is_room(&upload) {
        ingest_room(&state, &upload).await?;
    }
    let artifact = repo::finish_upload_with_artifact(&state.db, &upload, &sha256).await?;
    Ok(Json(artifact))
}

#[utoipa::path(
    post, path = "/v1/scans/{scan_id}/uploads/{upload_id}/abort", tag = "uploads",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path), ("upload_id" = Uuid, Path)),
    responses((status = 204), (status = 404, body = ErrorBody), (status = 409, body = ErrorBody))
)]
pub async fn abort_upload(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path((scan_id, upload_id)): Path<(Uuid, Uuid)>,
) -> ApiResult<StatusCode> {
    let upload = open_upload(&state, user_id, scan_id, upload_id).await?;
    if upload.state == "aborted" {
        return Ok(StatusCode::NO_CONTENT);
    }
    require_open(&upload)?;
    state
        .storage
        .abort_multipart(&upload.s3_key, &upload.s3_upload_id)
        .await
        .map_err(storage_error)?;
    repo::set_upload_state(&state.db, upload.id, "aborted").await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(
    get, path = "/v1/scans/{scan_id}/artifacts", tag = "uploads",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    responses((status = 200, body = Vec<Artifact>), (status = 404, body = ErrorBody))
)]
pub async fn list_artifacts(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
) -> ApiResult<Json<Vec<Artifact>>> {
    get_owned_scan(&state.db, user_id, scan_id).await?;
    Ok(Json(repo::list_artifacts(&state.db, scan_id).await?))
}
