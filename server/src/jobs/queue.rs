use std::time::Duration;

use anyhow::Result;
use serde::Serialize;
use serde_json::Value;
use sqlx::{FromRow, PgPool};
use uuid::Uuid;

pub const LEASE_GRACE_SECS: i32 = 5;
pub const MAX_BACKOFF_SECS: f64 = 300.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum JobKind {
    TextureBake,
}

impl JobKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::TextureBake => "texture_bake",
        }
    }
}

#[derive(Clone, Debug, FromRow, Serialize)]
pub struct Job {
    pub id: Uuid,
    pub kind: String,
    pub payload: Value,
    pub attempts: i32,
    pub max_attempts: i32,
    pub deadline_secs: i32,
}

#[derive(Clone, Copy, Debug)]
pub struct EnqueueOptions {
    pub max_attempts: i32,
    pub deadline_secs: i32,
    pub delay: Duration,
}

impl Default for EnqueueOptions {
    fn default() -> Self {
        Self {
            max_attempts: 5,
            deadline_secs: 600,
            delay: Duration::ZERO,
        }
    }
}

pub async fn enqueue(
    db: &PgPool,
    kind: &str,
    payload: &Value,
    options: EnqueueOptions,
) -> Result<Uuid> {
    let id = Uuid::new_v4();
    sqlx::query(
        "INSERT INTO jobs (id, kind, payload, max_attempts, deadline_secs, run_at)
         VALUES ($1, $2, $3, $4, $5, now() + make_interval(secs => $6))",
    )
    .bind(id)
    .bind(kind)
    .bind(payload)
    .bind(options.max_attempts)
    .bind(options.deadline_secs)
    .bind(options.delay.as_secs_f64())
    .execute(db)
    .await?;
    Ok(id)
}

pub async fn bury_exhausted(db: &PgPool) -> Result<u64> {
    let result = sqlx::query(
        "UPDATE jobs SET state = 'dead', finished_at = now(), locked_until = NULL,
                last_error = COALESCE(last_error, 'lease expired after the final attempt')
         WHERE state = 'running' AND locked_until < now() AND attempts >= max_attempts",
    )
    .execute(db)
    .await?;
    Ok(result.rows_affected())
}

pub async fn claim_next(db: &PgPool, worker_id: &str) -> Result<Option<Job>> {
    bury_exhausted(db).await?;
    let job = sqlx::query_as(
        "WITH next AS (
             SELECT id FROM jobs
             WHERE (state = 'queued' AND run_at <= now())
                OR (state = 'running' AND locked_until < now() AND attempts < max_attempts)
             ORDER BY run_at
             FOR UPDATE SKIP LOCKED
             LIMIT 1
         )
         UPDATE jobs SET state = 'running', attempts = attempts + 1, locked_by = $1,
                locked_until = now() + make_interval(secs => deadline_secs + $2)
         FROM next WHERE jobs.id = next.id
         RETURNING jobs.id, jobs.kind, jobs.payload, jobs.attempts, jobs.max_attempts,
                   jobs.deadline_secs",
    )
    .bind(worker_id)
    .bind(LEASE_GRACE_SECS)
    .fetch_optional(db)
    .await?;
    Ok(job)
}

pub async fn mark_done(db: &PgPool, job_id: Uuid, worker_id: &str) -> Result<()> {
    sqlx::query(
        "UPDATE jobs SET state = 'done', finished_at = now(), locked_until = NULL, locked_by = NULL
         WHERE id = $1 AND state = 'running' AND locked_by = $2",
    )
    .bind(job_id)
    .bind(worker_id)
    .execute(db)
    .await?;
    Ok(())
}

pub fn retry_delay(attempts: i32, base: Duration) -> Duration {
    let factor = 2f64.powi(attempts.saturating_sub(1).min(16));
    Duration::from_secs_f64((base.as_secs_f64() * factor).min(MAX_BACKOFF_SECS))
}

pub async fn mark_failed(
    db: &PgPool,
    job: &Job,
    worker_id: &str,
    error: &str,
    retry_base: Duration,
) -> Result<()> {
    let delay = retry_delay(job.attempts, retry_base).as_secs_f64();
    sqlx::query(
        "UPDATE jobs SET
            state = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END,
            run_at = now() + make_interval(secs => $4),
            last_error = $3,
            locked_until = NULL, locked_by = NULL,
            finished_at = CASE WHEN attempts >= max_attempts THEN now() END
         WHERE id = $1 AND state = 'running' AND locked_by = $2",
    )
    .bind(job.id)
    .bind(worker_id)
    .bind(error)
    .bind(delay)
    .execute(db)
    .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backoff_doubles_and_caps() {
        let base = Duration::from_secs(2);
        assert_eq!(retry_delay(1, base), Duration::from_secs(2));
        assert_eq!(retry_delay(2, base), Duration::from_secs(4));
        assert_eq!(retry_delay(20, base), Duration::from_secs(300));
    }
}
