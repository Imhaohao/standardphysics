use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::storage::{PresignedPart, UploadedPart};

#[derive(Clone, Debug, Serialize, FromRow, ToSchema)]
pub struct Upload {
    pub id: Uuid,
    pub scan_id: Uuid,
    pub kind: String,
    pub filename: String,
    pub content_type: String,
    pub size_bytes: i64,
    pub part_size: i64,
    pub part_count: i32,
    pub state: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Clone, Debug, FromRow)]
pub struct UploadRecord {
    pub id: Uuid,
    pub scan_id: Uuid,
    pub kind: String,
    pub filename: String,
    pub content_type: String,
    pub size_bytes: i64,
    pub part_size: i64,
    pub part_count: i32,
    pub s3_key: String,
    pub s3_upload_id: String,
    pub state: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Clone, Debug, Serialize, FromRow, ToSchema)]
pub struct Artifact {
    pub id: Uuid,
    pub scan_id: Uuid,
    pub upload_id: Uuid,
    pub kind: String,
    pub filename: String,
    pub content_type: String,
    pub size_bytes: i64,
    pub sha256: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Clone, Deserialize, Serialize, ToSchema)]
pub struct CreateUpload {
    pub kind: String,
    pub filename: String,
    pub content_type: String,
    pub size_bytes: i64,
    pub part_size: Option<i64>,
}

#[derive(Serialize, ToSchema)]
pub struct UploadStatus {
    pub upload: Upload,
    pub uploaded_parts: Vec<UploadedPart>,
}

#[derive(Deserialize, ToSchema)]
pub struct PresignRequest {
    pub part_numbers: Vec<i32>,
}

#[derive(Serialize, ToSchema)]
pub struct PresignResponse {
    /// Host (with port when not default) every URL in `parts` points at; allowlist this on the device.
    pub host: Option<String>,
    pub parts: Vec<PresignedPart>,
    pub expires_in_secs: u64,
}

#[derive(Deserialize, ToSchema)]
pub struct CompleteUpload {
    pub sha256: String,
}

impl UploadRecord {
    pub fn public(&self) -> Upload {
        Upload {
            id: self.id,
            scan_id: self.scan_id,
            kind: self.kind.clone(),
            filename: self.filename.clone(),
            content_type: self.content_type.clone(),
            size_bytes: self.size_bytes,
            part_size: self.part_size,
            part_count: self.part_count,
            state: self.state.clone(),
            created_at: self.created_at,
        }
    }
}
