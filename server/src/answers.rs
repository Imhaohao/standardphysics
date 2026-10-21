//! Owner answers to the questions findings ask. Each answer is stored per scan, subject and
//! metric, becomes an owner observation in the scene, and saving answers re-runs the rules.

use anyhow::Result;
use axum::extract::{Path, State};
use axum::Json;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sqlx::PgPool;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::assessments;
use crate::auth::AuthUser;
use crate::engine::answer_unit;
use crate::error::{ApiError, ApiResult, ErrorBody};
use crate::finish::pipeline::run_reassessment;
use crate::scans::models::Report;
use crate::scans::repo::get_owned_scan;
use crate::state::AppState;

const MAX_ANSWERS_PER_REQUEST: usize = 500;
const MAX_TEXT_ANSWER_LEN: usize = 500;

#[derive(Clone, Debug, Serialize, ToSchema, sqlx::FromRow)]
pub struct Answer {
    pub subject_id: String,
    pub metric: String,
    /// `true`/`false`, a number in the question's unit, or text.
    #[schema(value_type = Object)]
    pub value: sqlx::types::Json<Value>,
    /// `owner` when typed in, `photo` when read from a photo by the vision model.
    pub source: String,
    pub confidence: f64,
    pub photo_artifact_id: Option<Uuid>,
    pub answered_at: DateTime<Utc>,
}

#[derive(Debug, Deserialize, Serialize, ToSchema)]
pub struct AnswerInput {
    pub subject_id: String,
    pub metric: String,
    /// `null` removes the answer.
    #[schema(value_type = Object)]
    pub value: Value,
}

#[derive(Debug, Deserialize, Serialize, ToSchema)]
pub struct SaveAnswers {
    pub answers: Vec<AnswerInput>,
}

pub fn observation_id(subject_id: &str, metric: &str) -> String {
    format!("owner:{subject_id}:{metric}")
}

fn observation(answer: &Answer) -> Value {
    json!({
        "id": observation_id(&answer.subject_id, &answer.metric),
        "subject_id": answer.subject_id,
        "metric": answer.metric,
        "value": answer.value.0,
        "unit": answer_unit(&answer.metric).filter(|u| !u.is_empty()),
        "source": answer.source,
        "confidence": answer.confidence,
    })
}

pub(crate) async fn list(db: &PgPool, scan_id: Uuid) -> Result<Vec<Answer>> {
    Ok(sqlx::query_as(
        "SELECT subject_id, metric, value, source, confidence, photo_artifact_id, answered_at
         FROM scan_answers
         WHERE scan_id = $1 ORDER BY subject_id, metric",
    )
    .bind(scan_id)
    .fetch_all(db)
    .await?)
}

/// The scan's owner answers as sp-core scene observations.
pub async fn answer_observations(db: &PgPool, scan_id: Uuid) -> Result<Vec<Value>> {
    Ok(list(db, scan_id).await?.iter().map(observation).collect())
}

fn check_value(value: &Value) -> ApiResult<()> {
    let acceptable = match value {
        Value::Null | Value::Bool(_) => true,
        Value::Number(n) => n.as_f64().is_some_and(f64::is_finite),
        Value::String(s) => s.chars().count() <= MAX_TEXT_ANSWER_LEN,
        _ => false,
    };
    if acceptable {
        Ok(())
    } else {
        Err(ApiError::bad_request(
            "an answer is true/false, a number, short text, or null",
        ))
    }
}

pub(crate) fn check_known_metric(subject_id: &str, metric: &str) -> ApiResult<()> {
    if subject_id.trim().is_empty() {
        return Err(ApiError::bad_request("subject_id is required"));
    }
    if answer_unit(metric).is_none() {
        return Err(ApiError::bad_request(format!(
            "{metric} is not a known metric"
        )));
    }
    Ok(())
}

fn check_input(input: &AnswerInput) -> ApiResult<()> {
    check_known_metric(&input.subject_id, &input.metric)?;
    check_value(&input.value)
}

async fn store(db: &PgPool, scan_id: Uuid, answers: &[AnswerInput]) -> Result<()> {
    let mut tx = db.begin().await?;
    for input in answers {
        if input.value.is_null() {
            sqlx::query(
                "DELETE FROM scan_answers WHERE scan_id = $1 AND subject_id = $2 AND metric = $3",
            )
            .bind(scan_id)
            .bind(&input.subject_id)
            .bind(&input.metric)
            .execute(&mut *tx)
            .await?;
            continue;
        }
        sqlx::query(
            "INSERT INTO scan_answers (scan_id, subject_id, metric, value) VALUES ($1, $2, $3, $4)
             ON CONFLICT (scan_id, subject_id, metric)
             DO UPDATE SET value = EXCLUDED.value, source = 'owner', confidence = 1,
                           photo_artifact_id = NULL, answered_at = now()",
        )
        .bind(scan_id)
        .bind(&input.subject_id)
        .bind(&input.metric)
        .bind(sqlx::types::Json(&input.value))
        .execute(&mut *tx)
        .await?;
    }
    tx.commit().await?;
    Ok(())
}

#[utoipa::path(
    get, path = "/v1/scans/{scan_id}/answers", tag = "answers",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    responses((status = 200, body = Vec<Answer>), (status = 404, body = ErrorBody))
)]
pub async fn list_answers(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
) -> ApiResult<Json<Vec<Answer>>> {
    get_owned_scan(&state.db, user_id, scan_id).await?;
    Ok(Json(list(&state.db, scan_id).await?))
}

#[utoipa::path(
    put, path = "/v1/scans/{scan_id}/answers", tag = "answers",
    security(("bearer" = [])),
    params(("scan_id" = Uuid, Path)),
    request_body = SaveAnswers,
    responses(
        (status = 200, body = Report, description = "The report re-evaluated with every saved answer"),
        (status = 400, body = ErrorBody),
        (status = 404, body = ErrorBody),
        (status = 409, body = ErrorBody, description = "The scan has not been finished yet"),
    )
)]
pub async fn save_answers(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(scan_id): Path<Uuid>,
    Json(body): Json<SaveAnswers>,
) -> ApiResult<Json<Report>> {
    get_owned_scan(&state.db, user_id, scan_id).await?;
    if body.answers.len() > MAX_ANSWERS_PER_REQUEST {
        return Err(ApiError::bad_request("too many answers in one request"));
    }
    body.answers.iter().try_for_each(check_input)?;
    if assessments::latest_report(&state.db, scan_id)
        .await?
        .is_none()
    {
        return Err(ApiError::Conflict(
            "finish the scan before answering its questions".into(),
        ));
    }
    store(&state.db, scan_id, &body.answers).await?;
    Ok(Json(run_reassessment(&state, scan_id).await?))
}
