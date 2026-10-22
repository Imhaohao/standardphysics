//! Photo evidence: the owner photographs what a finding asks about and the vision model
//! answers the question from the photo. The reading is saved like an owner answer, with
//! source `photo` and the model's confidence, and the report is evaluated again.

use axum::extract::{Path, State};
use axum::Json;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::PgPool;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::answers::check_known_metric;
use crate::assessments;
use crate::auth::AuthUser;
use crate::error::{ApiError, ApiResult, ErrorBody};
use crate::findings::Ask;
use crate::finish::pipeline::run_reassessment;
use crate::scans::models::Report;
use crate::scans::repo::get_owned_scan;
use crate::state::AppState;
use crate::vision::{PhotoQuestion, PhotoReading, PhotoRef};
use crate::vision_cache::{self, cache_key};

/// Below this the reading is shown to the owner but not used as an answer.
const MIN_PHOTO_CONFIDENCE: f64 = 0.6;

#[derive(Debug, Deserialize, Serialize, ToSchema)]
pub struct PhotoAnswerRequest {
    pub subject_id: String,
    pub metric: String,
    /// A completed upload of kind `photo` on this scan.
    pub artifact_id: Uuid,
}

#[derive(Serialize, ToSchema)]
pub struct PhotoAnswerResponse {
    /// True when the photo settled the question; false when it was unclear and the owner
    /// should answer or try another photo.
    pub answered: bool,
    #[schema(value_type = Option<Object>)]
    pub answer: Option<Value>,
    pub confidence: f64,
    pub report: Report,
}

async fn latest_report(db: &PgPool, scan_id: Uuid) -> ApiResult<Report> {
    assessments::latest_report(db, scan_id)
        .await?
        .ok_or_else(|| ApiError::Conflict("finish the scan before adding photos".into()))
}

async fn find_ask(state: &AppState, scan_id: Uuid, body: &PhotoAnswerRequest) -> ApiResult<Ask> {
    latest_report(&state.db, scan_id)
        .await?
        .findings
        .into_iter()
        .filter_map(|f| f.ask)
        .find(|a| a.subject_id == body.subject_id && a.metric == body.metric)
        .ok_or_else(|| ApiError::bad_request("no open question matches this subject and metric"))
}

async fn photo_location(db: &PgPool, scan_id: Uuid, artifact_id: Uuid) -> ApiResult<PhotoRef> {
    let row: Option<(String, String, String)> = sqlx::query_as(
        "SELECT s3_key, content_type, sha256 FROM artifacts
         WHERE id = $1 AND scan_id = $2 AND kind = 'photo'",
    )
    .bind(artifact_id)
    .bind(scan_id)
    .fetch_optional(db)
    .await?;
    let (key, content_type, sha256) =
        row.ok_or_else(|| ApiError::bad_request("artifact_id is not a photo on this scan"))?;
    Ok(PhotoRef {
        key,
        content_type,
        sha256,
    })
}

async fn save_reading(
    db: &PgPool,
    scan_id: Uuid,
    body: &PhotoAnswerRequest,
    answer: &Value,
    confidence: f64,
) -> ApiResult<()> {
    sqlx::query(
        "INSERT INTO scan_answers
             (scan_id, subject_id, metric, value, source, confidence, photo_artifact_id)
         VALUES ($1, $2, $3, $4, 'photo', $5, $6)
         ON CONFLICT (scan_id, subject_id, metric) DO UPDATE SET
             value = EXCLUDED.value, source = 'photo', confidence = EXCLUDED.confidence,
             photo_artifact_id = EXCLUDED.photo_artifact_id, answered_at = now()",
    )
    .bind(scan_id)
    .bind(&body.subject_id)
    .bind(&body.metric)
    .bind(sqlx::types::Json(answer))
    .bind(confidence)
    .bind(body.artifact_id)
    .execute(db)
    .await?;
    Ok(())
}

fn question(ask: Ask) -> PhotoQuestion {
    PhotoQuestion {
        prompt: ask.prompt,
        value_type: ask.value_type,
        unit: ask.unit,
        options: ask.options,
    }
}

fn photo_cache_key(model: &str, photo: &PhotoRef, q: &PhotoQuestion) -> String {
    let options = q.options.join(",");
    cache_key(&[
        "photo",
        model,
        &q.prompt,
        &q.value_type,
        &q.unit,
        &options,
        &photo.sha256,
    ])
}

/// The same photo asked the same question is read once; retakes are new photos and new reads.
async fn read_photo_cached(
    state: &AppState,
    photo: &PhotoRef,
    question: &PhotoQuestion,
) -> ApiResult<PhotoReading> {
    let key = photo_cache_key(state.labeller.model(), photo, question);
    let cached = vision_cache::lookup(&state.db, std::slice::from_ref(&key)).await?;
    if let Some(reply) = cached.get(&key) {
        return Ok(PhotoReading {
            answer: reply.get("answer").filter(|a| !a.is_null()).cloned(),
            confidence: reply
                .get("confidence")
                .and_then(Value::as_f64)
                .unwrap_or(0.0),
        });
    }
    let reading = state
        .labeller
        .read_photo(&state.storage, photo, question)
        .await
        .map_err(|err| ApiError::Storage(format!("vision model: {err}")))?;
    let reply = serde_json::json!({"answer": reading.answer, "confidence": reading.confidence});
    vision_cache::store(&state.db, &[(key, reply)]).await?;
    Ok(reading)
}

fn confident_answer(reading: &PhotoReading) -> Option<&Value> {
    reading
        .answer
        .as_ref()
        .filter(|_| reading.confidence >= MIN_PHOTO_CONFIDENCE)
}

#[utoipa::path(
    post, path = "/v1/scans/{scan_id}/photo-answers", tag = "answers",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    request_body = PhotoAnswerRequest,
    responses(
        (status = 200, body = PhotoAnswerResponse),
        (status = 400, body = ErrorBody),
        (status = 404, body = ErrorBody),
        (status = 409, body = ErrorBody, description = "The scan is not finished, or photo reading is not set up on this server"),
        (status = 502, body = ErrorBody, description = "The vision model did not give a usable reply"),
    )
)]
pub async fn answer_from_photo(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
    Json(body): Json<PhotoAnswerRequest>,
) -> ApiResult<Json<PhotoAnswerResponse>> {
    get_owned_scan(&state.db, user_id, scan_id).await?;
    check_known_metric(&body.subject_id, &body.metric)?;
    if !state.labeller.is_enabled() {
        return Err(ApiError::Conflict(
            "photo reading is not set up on this server".into(),
        ));
    }
    let ask = find_ask(&state, scan_id, &body).await?;
    let photo = photo_location(&state.db, scan_id, body.artifact_id).await?;
    let reading = read_photo_cached(&state, &photo, &question(ask)).await?;
    let answer = confident_answer(&reading).cloned();
    let report = match &answer {
        Some(value) => {
            save_reading(&state.db, scan_id, &body, value, reading.confidence).await?;
            run_reassessment(&state, scan_id).await?
        }
        None => latest_report(&state.db, scan_id).await?,
    };
    Ok(Json(PhotoAnswerResponse {
        answered: answer.is_some(),
        answer: reading.answer,
        confidence: reading.confidence,
        report,
    }))
}
