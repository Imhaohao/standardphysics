use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{anyhow, Result};
use futures::future::BoxFuture;
use sqlx::PgPool;
use tokio::sync::{watch, Notify};
use uuid::Uuid;

use super::handlers::texture_bake;
use super::queue::{claim_next, mark_done, mark_failed, Job, JobKind};
use crate::storage::Storage;

#[derive(Clone)]
pub struct JobContext {
    pub db: PgPool,
    pub storage: Storage,
}

pub type HandlerFn = Arc<dyn Fn(JobContext, Job) -> BoxFuture<'static, Result<()>> + Send + Sync>;

#[derive(Clone, Default)]
pub struct Handlers {
    by_kind: HashMap<String, HandlerFn>,
}

impl Handlers {
    pub fn standard() -> Self {
        let mut handlers = Self::default();
        handlers.register(JobKind::TextureBake.as_str(), |ctx, job| {
            Box::pin(texture_bake(ctx, job))
        });
        handlers
    }

    pub fn register<F>(&mut self, kind: &str, handler: F)
    where
        F: Fn(JobContext, Job) -> BoxFuture<'static, Result<()>> + Send + Sync + 'static,
    {
        self.by_kind.insert(kind.to_string(), Arc::new(handler));
    }

    fn get(&self, kind: &str) -> Option<HandlerFn> {
        self.by_kind.get(kind).cloned()
    }
}

#[derive(Clone)]
pub struct JobWorker {
    ctx: JobContext,
    handlers: Handlers,
    worker_id: String,
    poll: Duration,
    retry_base: Duration,
    wake: Arc<Notify>,
}

impl JobWorker {
    pub fn new(ctx: JobContext, handlers: Handlers, poll: Duration, wake: Arc<Notify>) -> Self {
        Self {
            ctx,
            handlers,
            worker_id: format!("worker-{}", Uuid::new_v4()),
            poll,
            retry_base: Duration::from_secs(2),
            wake,
        }
    }

    pub fn with_retry_base(mut self, retry_base: Duration) -> Self {
        self.retry_base = retry_base;
        self
    }

    pub async fn run(self, mut shutdown: watch::Receiver<bool>) {
        loop {
            if *shutdown.borrow() {
                return;
            }
            match self.run_once().await {
                Ok(true) => continue,
                Ok(false) => {}
                Err(err) => tracing::error!(error = ?err, "job worker iteration failed"),
            }
            tokio::select! {
                _ = tokio::time::sleep(self.poll) => {}
                _ = self.wake.notified() => {}
                _ = shutdown.changed() => {}
            }
        }
    }

    pub async fn run_once(&self) -> Result<bool> {
        let Some(job) = claim_next(&self.ctx.db, &self.worker_id).await? else {
            return Ok(false);
        };
        let started = std::time::Instant::now();
        let outcome = self.execute(&job).await;
        self.record_outcome(&job, outcome, started.elapsed())
            .await?;
        Ok(true)
    }

    async fn execute(&self, job: &Job) -> Result<()> {
        let handler = self
            .handlers
            .get(&job.kind)
            .ok_or_else(|| anyhow!("no handler for job kind {}", job.kind))?;
        let deadline = Duration::from_secs(job.deadline_secs.max(1) as u64);
        let task = tokio::spawn(handler(self.ctx.clone(), job.clone()));
        match tokio::time::timeout(deadline, task).await {
            Err(_) => Err(anyhow!("job exceeded its {}s deadline", job.deadline_secs)),
            Ok(Err(join_error)) => Err(anyhow!("job handler crashed: {join_error}")),
            Ok(Ok(result)) => result,
        }
    }

    async fn record_outcome(&self, job: &Job, outcome: Result<()>, took: Duration) -> Result<()> {
        match outcome {
            Ok(()) => {
                tracing::info!(job_id = %job.id, kind = %job.kind, ms = took.as_millis() as u64, "job done");
                mark_done(&self.ctx.db, job.id, &self.worker_id).await
            }
            Err(err) => {
                tracing::warn!(job_id = %job.id, kind = %job.kind, attempt = job.attempts, error = %err, "job failed");
                let message = format!("{err:#}");
                mark_failed(
                    &self.ctx.db,
                    job,
                    &self.worker_id,
                    &message,
                    self.retry_base,
                )
                .await
            }
        }
    }
}
