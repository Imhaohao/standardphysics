use sqlx::PgPool;
use uuid::Uuid;

use super::models::Scan;
use crate::error::{ApiError, ApiResult};

const SCAN_COLUMNS: &str = "id, name, site_name, status, created_at, updated_at";

pub async fn insert_scan(
    db: &PgPool,
    user_id: Uuid,
    name: &str,
    site_name: Option<&str>,
) -> ApiResult<Scan> {
    let scan = sqlx::query_as(&format!(
        "INSERT INTO scans (id, user_id, name, site_name) VALUES ($1, $2, $3, $4)
         RETURNING {SCAN_COLUMNS}"
    ))
    .bind(Uuid::new_v4())
    .bind(user_id)
    .bind(name)
    .bind(site_name)
    .fetch_one(db)
    .await?;
    Ok(scan)
}

pub async fn list_scans(db: &PgPool, user_id: Uuid) -> ApiResult<Vec<Scan>> {
    let scans = sqlx::query_as(&format!(
        "SELECT {SCAN_COLUMNS} FROM scans WHERE user_id = $1 ORDER BY created_at DESC LIMIT 200"
    ))
    .bind(user_id)
    .fetch_all(db)
    .await?;
    Ok(scans)
}

pub async fn get_owned_scan(db: &PgPool, user_id: Uuid, scan_id: Uuid) -> ApiResult<Scan> {
    let scan: Option<Scan> = sqlx::query_as(&format!(
        "SELECT {SCAN_COLUMNS} FROM scans WHERE id = $1 AND user_id = $2"
    ))
    .bind(scan_id)
    .bind(user_id)
    .fetch_optional(db)
    .await?;
    scan.ok_or(ApiError::NotFound)
}

pub async fn set_status(db: &PgPool, scan_id: Uuid, status: &str) -> ApiResult<()> {
    sqlx::query("UPDATE scans SET status = $2, updated_at = now() WHERE id = $1")
        .bind(scan_id)
        .bind(status)
        .execute(db)
        .await?;
    Ok(())
}

pub async fn get_scan_by_id(db: &PgPool, scan_id: Uuid) -> ApiResult<Scan> {
    let scan: Option<Scan> =
        sqlx::query_as(&format!("SELECT {SCAN_COLUMNS} FROM scans WHERE id = $1"))
            .bind(scan_id)
            .fetch_optional(db)
            .await?;
    scan.ok_or(ApiError::NotFound)
}

pub async fn rename_scan(
    db: &PgPool,
    scan_id: Uuid,
    name: Option<&str>,
    site_name: Option<Option<&str>>,
) -> ApiResult<Scan> {
    let scan = sqlx::query_as(&format!(
        "UPDATE scans SET name = COALESCE($2, name),
                site_name = CASE WHEN $3 THEN $4 ELSE site_name END,
                updated_at = now()
         WHERE id = $1 RETURNING {SCAN_COLUMNS}"
    ))
    .bind(scan_id)
    .bind(name)
    .bind(site_name.is_some())
    .bind(site_name.flatten())
    .fetch_one(db)
    .await?;
    Ok(scan)
}
