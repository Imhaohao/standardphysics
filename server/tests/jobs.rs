mod common;

use std::collections::HashMap;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use common::TestApp;
use serde_json::json;
use sp_server::jobs::queue::{claim_next, enqueue, EnqueueOptions};
use sp_server::jobs::worker::{Handlers, JobWorker};
use sqlx::PgPool;
use uuid::Uuid;

fn worker(app: &TestApp, handlers: Handlers) -> JobWorker {
    JobWorker::new(
        app.state.job_context(),
        handlers,
        Duration::from_millis(20),
        app.state.job_wake.clone(),
    )
    .with_retry_base(Duration::from_millis(10))
}

async fn job_row(db: &PgPool, id: Uuid) -> (String, i32, Option<String>) {
    sqlx::query_as("SELECT state, attempts, last_error FROM jobs WHERE id = $1")
        .bind(id)
        .fetch_one(db)
        .await
        .unwrap()
}

async fn drain(worker: &JobWorker) {
    for _ in 0..200 {
        if !worker.run_once().await.unwrap() {
            tokio::time::sleep(Duration::from_millis(120)).await;
            if !worker.run_once().await.unwrap() {
                return;
            }
        }
    }
}

#[tokio::test]
async fn standard_texture_bake_stub_completes() {
    let app = TestApp::start().await;
    let id = enqueue(
        &app.db,
        "texture_bake",
        &json!({"scan_id": "x"}),
        EnqueueOptions::default(),
    )
    .await
    .unwrap();
    drain(&worker(&app, Handlers::standard())).await;
    assert_eq!(job_row(&app.db, id).await.0, "done");
}

#[tokio::test]
async fn failing_job_is_retried_then_succeeds() {
    let app = TestApp::start().await;
    let attempts = Arc::new(AtomicUsize::new(0));
    let mut handlers = Handlers::default();
    let counter = Arc::clone(&attempts);
    handlers.register("flaky", move |_, _| {
        let counter = Arc::clone(&counter);
        Box::pin(async move {
            if counter.fetch_add(1, Ordering::SeqCst) < 2 {
                anyhow::bail!("transient failure");
            }
            Ok(())
        })
    });
    let id = enqueue(&app.db, "flaky", &json!({}), EnqueueOptions::default())
        .await
        .unwrap();
    let worker = worker(&app, handlers);
    drain(&worker).await;
    let (state, used, _) = job_row(&app.db, id).await;
    assert_eq!((state.as_str(), used), ("done", 3));
}

#[tokio::test]
async fn job_that_keeps_failing_ends_dead_with_its_error() {
    let app = TestApp::start().await;
    let mut handlers = Handlers::default();
    handlers.register("doomed", |_, _| {
        Box::pin(async { anyhow::bail!("always broken") })
    });
    let options = EnqueueOptions {
        max_attempts: 2,
        ..EnqueueOptions::default()
    };
    let id = enqueue(&app.db, "doomed", &json!({}), options)
        .await
        .unwrap();
    drain(&worker(&app, handlers)).await;
    let (state, attempts, error) = job_row(&app.db, id).await;
    assert_eq!((state.as_str(), attempts), ("dead", 2));
    assert!(error.unwrap().contains("always broken"));
}

#[tokio::test]
async fn unknown_kind_and_panics_are_failures_not_crashes() {
    let app = TestApp::start().await;
    let mut handlers = Handlers::default();
    handlers.register("panicky", |_, _| Box::pin(async { panic!("boom") }));
    let options = EnqueueOptions {
        max_attempts: 1,
        ..EnqueueOptions::default()
    };
    let unknown = enqueue(&app.db, "mystery", &json!({}), options)
        .await
        .unwrap();
    let panicky = enqueue(&app.db, "panicky", &json!({}), options)
        .await
        .unwrap();
    drain(&worker(&app, handlers)).await;
    assert_eq!(job_row(&app.db, unknown).await.0, "dead");
    let (state, _, error) = job_row(&app.db, panicky).await;
    assert_eq!(state, "dead");
    assert!(error.unwrap().contains("crashed"));
}

#[tokio::test]
async fn job_past_its_deadline_is_failed_and_retried() {
    let app = TestApp::start().await;
    let mut handlers = Handlers::default();
    handlers.register("slow", |_, _| {
        Box::pin(async {
            tokio::time::sleep(Duration::from_secs(30)).await;
            Ok(())
        })
    });
    let options = EnqueueOptions {
        max_attempts: 2,
        deadline_secs: 1,
        ..EnqueueOptions::default()
    };
    let id = enqueue(&app.db, "slow", &json!({}), options).await.unwrap();
    let worker = worker(&app, handlers);
    assert!(worker.run_once().await.unwrap());
    let (state, attempts, error) = job_row(&app.db, id).await;
    assert_eq!((state.as_str(), attempts), ("queued", 1));
    assert!(error.unwrap().contains("deadline"));
}

#[tokio::test]
async fn timed_out_handler_is_stopped_not_left_running() {
    let app = TestApp::start().await;
    let finished = Arc::new(AtomicUsize::new(0));
    let mut handlers = Handlers::default();
    let counter = finished.clone();
    handlers.register("overrun", move |_, _| {
        let counter = counter.clone();
        Box::pin(async move {
            tokio::time::sleep(Duration::from_millis(1500)).await;
            counter.fetch_add(1, Ordering::SeqCst);
            Ok(())
        })
    });
    let options = EnqueueOptions {
        max_attempts: 1,
        deadline_secs: 1,
        ..EnqueueOptions::default()
    };
    enqueue(&app.db, "overrun", &json!({}), options)
        .await
        .unwrap();
    assert!(worker(&app, handlers).run_once().await.unwrap());
    tokio::time::sleep(Duration::from_millis(1000)).await;
    assert_eq!(
        finished.load(Ordering::SeqCst),
        0,
        "handler kept running after its deadline"
    );
}

#[tokio::test]
async fn crashed_worker_lease_expires_and_another_worker_recovers_the_job() {
    let app = TestApp::start().await;
    let id = enqueue(
        &app.db,
        "texture_bake",
        &json!({}),
        EnqueueOptions::default(),
    )
    .await
    .unwrap();
    let claimed = claim_next(&app.db, "worker-that-died")
        .await
        .unwrap()
        .unwrap();
    assert_eq!(claimed.id, id);
    assert!(
        claim_next(&app.db, "other").await.unwrap().is_none(),
        "lease still held"
    );

    sqlx::query("UPDATE jobs SET locked_until = now() - interval '1 second'")
        .execute(&app.db)
        .await
        .unwrap();
    drain(&worker(&app, Handlers::standard())).await;
    let (state, attempts, _) = job_row(&app.db, id).await;
    assert_eq!((state.as_str(), attempts), ("done", 2));
}

#[tokio::test]
async fn crash_on_the_final_attempt_buries_the_job() {
    let app = TestApp::start().await;
    let options = EnqueueOptions {
        max_attempts: 1,
        ..EnqueueOptions::default()
    };
    let id = enqueue(&app.db, "texture_bake", &json!({}), options)
        .await
        .unwrap();
    claim_next(&app.db, "worker-that-died")
        .await
        .unwrap()
        .unwrap();
    sqlx::query("UPDATE jobs SET locked_until = now() - interval '1 second'")
        .execute(&app.db)
        .await
        .unwrap();
    assert!(claim_next(&app.db, "other").await.unwrap().is_none());
    assert_eq!(job_row(&app.db, id).await.0, "dead");
}

#[tokio::test]
async fn concurrent_workers_run_each_job_exactly_once() {
    let app = TestApp::start().await;
    let seen: Arc<Mutex<HashMap<Uuid, usize>>> = Arc::default();
    let mut handlers = Handlers::default();
    let log = Arc::clone(&seen);
    handlers.register("count", move |_, job| {
        let log = Arc::clone(&log);
        Box::pin(async move {
            *log.lock().unwrap().entry(job.id).or_default() += 1;
            tokio::time::sleep(Duration::from_millis(5)).await;
            Ok(())
        })
    });
    for _ in 0..30 {
        enqueue(&app.db, "count", &json!({}), EnqueueOptions::default())
            .await
            .unwrap();
    }
    let tasks: Vec<_> = (0..4)
        .map(|_| {
            let worker = worker(&app, handlers.clone());
            tokio::spawn(async move { drain(&worker).await })
        })
        .collect();
    for task in tasks {
        task.await.unwrap();
    }
    let seen = seen.lock().unwrap();
    assert_eq!(seen.len(), 30);
    assert!(seen.values().all(|runs| *runs == 1));
}

#[tokio::test]
async fn delayed_jobs_wait_for_their_time() {
    let app = TestApp::start().await;
    let options = EnqueueOptions {
        delay: Duration::from_secs(3600),
        ..EnqueueOptions::default()
    };
    enqueue(&app.db, "texture_bake", &json!({}), options)
        .await
        .unwrap();
    assert!(!worker(&app, Handlers::standard()).run_once().await.unwrap());
}
