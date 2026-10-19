use anyhow::Result;
use sp_server::config::Config;
use sp_server::jobs::worker::{Handlers, JobWorker};
use sp_server::state::AppState;
use tokio::sync::watch;
use tracing_subscriber::EnvFilter;

fn init_tracing() {
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    let builder = tracing_subscriber::fmt().with_env_filter(filter);
    if std::env::var("LOG_FORMAT").as_deref() == Ok("json") {
        builder.json().init();
    } else {
        builder.init();
    }
}

async fn shutdown_signal() {
    let ctrl_c = async {
        let _ = tokio::signal::ctrl_c().await;
    };
    #[cfg(unix)]
    let terminate = async {
        if let Ok(mut term) =
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        {
            term.recv().await;
        }
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();
    tokio::select! {
        _ = ctrl_c => {}
        _ = terminate => {}
    }
}

async fn serve() -> Result<()> {
    let cfg = Config::from_env()?;
    let bind_addr = cfg.bind_addr.clone();
    let run_worker = cfg.run_job_worker;
    let poll = cfg.job_poll;
    let state = AppState::connect(cfg).await?;

    let (stop_tx, stop_rx) = watch::channel(false);
    let worker_task = run_worker.then(|| {
        let worker = JobWorker::new(
            state.job_context(),
            Handlers::standard(),
            poll,
            state.job_wake.clone(),
        );
        tokio::spawn(worker.run(stop_rx))
    });

    let listener = tokio::net::TcpListener::bind(&bind_addr).await?;
    tracing::info!(%bind_addr, "sp-server listening");
    axum::serve(listener, sp_server::build_router(state))
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    let _ = stop_tx.send(true);
    if let Some(task) = worker_task {
        let _ = task.await;
    }
    Ok(())
}

async fn migrate_only() -> Result<()> {
    let cfg = Config::from_env()?;
    let db = sp_server::db::connect(&cfg.database_url, cfg.db_max_connections).await?;
    sp_server::db::migrate(&db).await
}

#[tokio::main]
async fn main() -> Result<()> {
    init_tracing();
    match std::env::args().nth(1).as_deref() {
        None | Some("serve") => serve().await,
        Some("migrate") => migrate_only().await,
        Some("openapi") => {
            println!("{}", sp_server::openapi::openapi_json());
            Ok(())
        }
        Some(other) => anyhow::bail!("unknown command {other}; use serve, migrate or openapi"),
    }
}
