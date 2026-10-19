use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::findings::{Finding, Summary};

#[derive(Clone, Debug, Serialize, FromRow, ToSchema)]
pub struct Scan {
    pub id: Uuid,
    pub name: String,
    pub site_name: Option<String>,
    pub status: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Deserialize, Serialize, ToSchema)]
pub struct CreateScan {
    pub name: Option<String>,
    pub site_name: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, ToSchema)]
pub struct StageTimings {
    pub load_ms: u64,
    pub labelling_ms: u64,
    pub evaluation_ms: u64,
    pub persist_ms: u64,
    pub total_ms: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize, ToSchema)]
pub struct Report {
    pub scan_id: Uuid,
    pub assessment_id: Uuid,
    pub created_at: DateTime<Utc>,
    pub summary: Summary,
    pub findings: Vec<Finding>,
    pub timings: StageTimings,
    pub labelled_by_vision: u32,
    pub unlabelled_objects: u32,
}
