use anyhow::Result;
use chrono::{DateTime, Utc};
use serde_json::Value;
use sqlx::types::Json;
use sqlx::PgPool;
use uuid::Uuid;

use crate::findings::{Finding, Summary};
use crate::scans::models::{Report, StageTimings};

type AssessmentRow = (
    Uuid,
    DateTime<Utc>,
    Json<Vec<Finding>>,
    Json<Summary>,
    Json<Value>,
);

pub struct NewAssessment<'a> {
    pub scan_id: Uuid,
    pub findings: &'a [Finding],
    pub summary: &'a Summary,
    pub timings: &'a StageTimings,
    pub labelled_by_vision: u32,
    pub unlabelled_objects: u32,
}

pub async fn insert(db: &PgPool, new: &NewAssessment<'_>) -> Result<(Uuid, DateTime<Utc>)> {
    let id = Uuid::new_v4();
    let meta = serde_json::json!({
        "timings": new.timings,
        "labelled_by_vision": new.labelled_by_vision,
        "unlabelled_objects": new.unlabelled_objects,
    });
    let created_at: (DateTime<Utc>,) = sqlx::query_as(
        "INSERT INTO assessments (id, scan_id, findings, summary, timings_ms)
         VALUES ($1, $2, $3, $4, $5) RETURNING created_at",
    )
    .bind(id)
    .bind(new.scan_id)
    .bind(Json(new.findings))
    .bind(Json(new.summary))
    .bind(Json(meta))
    .fetch_one(db)
    .await?;
    Ok((id, created_at.0))
}

pub async fn latest_report(db: &PgPool, scan_id: Uuid) -> Result<Option<Report>> {
    let row: Option<AssessmentRow> = sqlx::query_as(
        "SELECT id, created_at, findings, summary, timings_ms FROM assessments
         WHERE scan_id = $1 ORDER BY created_at DESC LIMIT 1",
    )
    .bind(scan_id)
    .fetch_optional(db)
    .await?;
    row.map(|row| report_from_row(scan_id, row)).transpose()
}

fn report_from_row(scan_id: Uuid, row: AssessmentRow) -> Result<Report> {
    let (assessment_id, created_at, findings, summary, meta) = row;
    let meta = meta.0;
    Ok(Report {
        scan_id,
        assessment_id,
        created_at,
        summary: summary.0,
        findings: findings.0,
        timings: serde_json::from_value(meta["timings"].clone())?,
        labelled_by_vision: meta["labelled_by_vision"].as_u64().unwrap_or(0) as u32,
        unlabelled_objects: meta["unlabelled_objects"].as_u64().unwrap_or(0) as u32,
    })
}
