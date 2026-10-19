use std::sync::Arc;

use anyhow::Result;
use sqlx::PgPool;
use tokio::sync::Notify;

use crate::auth::apple::AppleVerifier;
use crate::config::Config;
use crate::jobs::worker::JobContext;
use crate::live::hub::LiveHub;
use crate::storage::Storage;
use crate::vision::Labeller;

#[derive(Clone)]
pub struct AppState {
    pub db: PgPool,
    pub storage: Storage,
    pub apple: Arc<AppleVerifier>,
    pub hub: Arc<LiveHub>,
    pub labeller: Labeller,
    pub cfg: Arc<Config>,
    pub job_wake: Arc<Notify>,
}

impl AppState {
    pub fn new(cfg: Config, db: PgPool) -> Self {
        Self {
            db,
            storage: Storage::new(&cfg.storage),
            apple: Arc::new(AppleVerifier::new(cfg.apple.clone())),
            hub: Arc::new(LiveHub::default()),
            labeller: Labeller::new(cfg.label.clone()),
            cfg: Arc::new(cfg),
            job_wake: Arc::new(Notify::new()),
        }
    }

    pub async fn connect(cfg: Config) -> Result<Self> {
        let db = crate::db::connect(&cfg.database_url, cfg.db_max_connections).await?;
        if cfg.run_migrations {
            crate::db::migrate(&db).await?;
        }
        Ok(Self::new(cfg, db))
    }

    pub fn job_context(&self) -> JobContext {
        JobContext {
            db: self.db.clone(),
            storage: self.storage.clone(),
        }
    }
}
