use std::time::Instant;

use anyhow::Result;
use serde_json::json;
use uuid::Uuid;

use super::labelling::{run_label_stage, LabelStage};
use crate::assessments::{self, NewAssessment};
use crate::engine::SceneEngine;
use crate::findings::{needs_info_finding, summarize, EvaluationReport, Finding};
use crate::jobs::queue::{enqueue, EnqueueOptions, JobKind};
use crate::live::protocol::ServerMessage;
use crate::live::rooms::{load_rooms, RoomState};
use crate::scans::models::{Report, StageTimings};
use crate::state::AppState;

fn elapsed_ms(since: Instant) -> u64 {
    since.elapsed().as_millis() as u64
}

async fn evaluate_rooms(rooms: Vec<RoomState>) -> Result<EvaluationReport> {
    tokio::task::spawn_blocking(move || {
        let mut engine = SceneEngine::new()?;
        let inputs: Vec<_> = rooms.iter().map(RoomState::to_input).collect();
        engine.load_rooms(&inputs)?;
        engine.evaluate_all()
    })
    .await?
}

fn unresolved_findings(stage: &LabelStage) -> Vec<Finding> {
    stage
        .unresolved
        .iter()
        .map(|item| {
            needs_info_finding(
                "label.unresolved",
                &item.observation_id,
                "This object could not be identified in time, so rules that depend on it need a manual check.",
            )
        })
        .collect()
}

pub async fn run_finish(state: &AppState, scan_id: Uuid) -> Result<Report> {
    let total = Instant::now();

    let stage_start = Instant::now();
    let mut rooms = load_rooms(&state.db, scan_id).await?;
    let load_ms = elapsed_ms(stage_start);

    let stage_start = Instant::now();
    let label_stage = run_label_stage(state, scan_id, &mut rooms).await?;
    let labelling_ms = elapsed_ms(stage_start);

    let stage_start = Instant::now();
    let evaluation = evaluate_rooms(rooms).await?;
    let mut findings = evaluation.findings;
    findings.extend(unresolved_findings(&label_stage));
    let evaluation_ms = elapsed_ms(stage_start);

    let stage_start = Instant::now();
    let mut summary = summarize(&findings);
    summary.governing = evaluation.governing;
    summary.governing_counts = evaluation.governing_counts;
    let mut timings = StageTimings {
        load_ms,
        labelling_ms,
        evaluation_ms,
        persist_ms: 0,
        total_ms: 0,
    };
    let new = NewAssessment {
        scan_id,
        findings: &findings,
        summary: &summary,
        timings: &timings,
        labelled_by_vision: label_stage.labelled,
        unlabelled_objects: label_stage.unresolved.len() as u32,
    };
    let (assessment_id, created_at) = assessments::insert(&state.db, &new).await?;
    timings.persist_ms = elapsed_ms(stage_start);
    timings.total_ms = elapsed_ms(total);

    tracing::info!(%scan_id, ?timings, findings = findings.len(), "finish pipeline timings");
    Ok(Report {
        scan_id,
        assessment_id,
        created_at,
        summary,
        findings,
        timings,
        labelled_by_vision: label_stage.labelled,
        unlabelled_objects: label_stage.unresolved.len() as u32,
    })
}

pub async fn after_finish(state: &AppState, report: &Report) -> Result<()> {
    enqueue(
        &state.db,
        JobKind::TextureBake.as_str(),
        &json!({"scan_id": report.scan_id}),
        EnqueueOptions::default(),
    )
    .await?;
    state.job_wake.notify_one();
    if let Some(session) = state.hub.peek(report.scan_id).await {
        if let Some(scene) = merged_scene(&state.db, report.scan_id).await? {
            session.publish(ServerMessage::Scene { scene });
        }
        session.publish(ServerMessage::Report {
            report: Box::new(report.clone()),
        });
    }
    Ok(())
}

pub async fn merged_scene(db: &sqlx::PgPool, scan_id: Uuid) -> Result<Option<serde_json::Value>> {
    let rooms = load_rooms(db, scan_id).await?;
    let inputs: Vec<_> = rooms.iter().map(RoomState::to_input).collect();
    tokio::task::spawn_blocking(move || crate::engine::assemble_scene(&inputs)).await?
}
