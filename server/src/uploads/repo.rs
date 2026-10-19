use sqlx::PgPool;
use uuid::Uuid;

use super::models::{Artifact, UploadRecord};
use crate::error::{ApiError, ApiResult};

const UPLOAD_COLUMNS: &str = "id, scan_id, kind, filename, content_type, size_bytes, part_size,
     part_count, s3_key, s3_upload_id, state, created_at";

pub async fn insert_upload(db: &PgPool, record: &UploadRecord) -> ApiResult<()> {
    sqlx::query(
        "INSERT INTO uploads (id, scan_id, kind, filename, content_type, size_bytes, part_size,
                              part_count, s3_key, s3_upload_id)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
    )
    .bind(record.id)
    .bind(record.scan_id)
    .bind(&record.kind)
    .bind(&record.filename)
    .bind(&record.content_type)
    .bind(record.size_bytes)
    .bind(record.part_size)
    .bind(record.part_count)
    .bind(&record.s3_key)
    .bind(&record.s3_upload_id)
    .execute(db)
    .await?;
    Ok(())
}

pub async fn get_upload(db: &PgPool, scan_id: Uuid, upload_id: Uuid) -> ApiResult<UploadRecord> {
    let record: Option<UploadRecord> = sqlx::query_as(&format!(
        "SELECT {UPLOAD_COLUMNS} FROM uploads WHERE id = $1 AND scan_id = $2"
    ))
    .bind(upload_id)
    .bind(scan_id)
    .fetch_optional(db)
    .await?;
    record.ok_or(ApiError::NotFound)
}

pub async fn set_upload_state(db: &PgPool, upload_id: Uuid, state: &str) -> ApiResult<()> {
    sqlx::query("UPDATE uploads SET state = $2, finished_at = now() WHERE id = $1")
        .bind(upload_id)
        .bind(state)
        .execute(db)
        .await?;
    Ok(())
}

pub async fn finish_upload_with_artifact(
    db: &PgPool,
    upload: &UploadRecord,
    sha256: &str,
) -> ApiResult<Artifact> {
    let mut tx = db.begin().await?;
    sqlx::query("UPDATE uploads SET state = 'complete', finished_at = now() WHERE id = $1")
        .bind(upload.id)
        .execute(&mut *tx)
        .await?;
    let artifact = sqlx::query_as(
        "INSERT INTO artifacts (id, scan_id, upload_id, kind, filename, content_type, s3_key,
                                size_bytes, sha256)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
         RETURNING id, scan_id, upload_id, kind, filename, content_type, size_bytes, sha256, created_at",
    )
    .bind(Uuid::new_v4())
    .bind(upload.scan_id)
    .bind(upload.id)
    .bind(&upload.kind)
    .bind(&upload.filename)
    .bind(&upload.content_type)
    .bind(&upload.s3_key)
    .bind(upload.size_bytes)
    .bind(sha256)
    .fetch_one(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(artifact)
}

pub async fn artifact_for_upload(db: &PgPool, upload_id: Uuid) -> ApiResult<Option<Artifact>> {
    let artifact = sqlx::query_as(
        "SELECT id, scan_id, upload_id, kind, filename, content_type, size_bytes, sha256, created_at
         FROM artifacts WHERE upload_id = $1",
    )
    .bind(upload_id)
    .fetch_optional(db)
    .await?;
    Ok(artifact)
}

pub async fn list_artifacts(db: &PgPool, scan_id: Uuid) -> ApiResult<Vec<Artifact>> {
    let artifacts = sqlx::query_as(
        "SELECT id, scan_id, upload_id, kind, filename, content_type, size_bytes, sha256, created_at
         FROM artifacts WHERE scan_id = $1 ORDER BY created_at",
    )
    .bind(scan_id)
    .fetch_all(db)
    .await?;
    Ok(artifacts)
}
