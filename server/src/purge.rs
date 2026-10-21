//! Removing a scan or a whole account, including the files the phone uploaded.

use anyhow::Result;
use sqlx::PgPool;
use uuid::Uuid;

use crate::storage::Storage;

struct StoredFiles {
    objects: Vec<String>,
    open_uploads: Vec<(String, String)>,
}

async fn stored_files(db: &PgPool, scan_ids: &[Uuid]) -> Result<StoredFiles> {
    let objects: Vec<(String,)> = sqlx::query_as(
        "SELECT s3_key FROM artifacts WHERE scan_id = ANY($1)
         UNION SELECT s3_key FROM uploads WHERE scan_id = ANY($1) AND state = 'complete'",
    )
    .bind(scan_ids)
    .fetch_all(db)
    .await?;
    let open_uploads: Vec<(String, String)> = sqlx::query_as(
        "SELECT s3_key, s3_upload_id FROM uploads WHERE scan_id = ANY($1) AND state = 'open'",
    )
    .bind(scan_ids)
    .fetch_all(db)
    .await?;
    Ok(StoredFiles {
        objects: objects.into_iter().map(|(key,)| key).collect(),
        open_uploads,
    })
}

/// Storage cleanup is best effort: the rows are already gone, so a failed delete only leaves
/// an unreachable object behind, which is logged for a manual sweep.
async fn delete_files(storage: &Storage, files: StoredFiles) {
    for key in &files.objects {
        if let Err(err) = storage.delete_object(key).await {
            tracing::warn!(error = %err, %key, "could not delete a stored file");
        }
    }
    for (key, upload_id) in &files.open_uploads {
        if let Err(err) = storage.abort_multipart(key, upload_id).await {
            tracing::warn!(error = %err, %key, "could not abort an open upload");
        }
    }
}

pub async fn delete_scan(db: &PgPool, storage: &Storage, scan_id: Uuid) -> Result<()> {
    let files = stored_files(db, &[scan_id]).await?;
    sqlx::query("DELETE FROM scans WHERE id = $1")
        .bind(scan_id)
        .execute(db)
        .await?;
    delete_files(storage, files).await;
    Ok(())
}

pub async fn delete_user(db: &PgPool, storage: &Storage, user_id: Uuid) -> Result<()> {
    let scan_ids: Vec<(Uuid,)> = sqlx::query_as("SELECT id FROM scans WHERE user_id = $1")
        .bind(user_id)
        .fetch_all(db)
        .await?;
    let scan_ids: Vec<Uuid> = scan_ids.into_iter().map(|(id,)| id).collect();
    let files = stored_files(db, &scan_ids).await?;
    sqlx::query("DELETE FROM users WHERE id = $1")
        .bind(user_id)
        .execute(db)
        .await?;
    delete_files(storage, files).await;
    Ok(())
}
