use std::collections::BTreeMap;
use std::time::Instant;

use anyhow::Result;
use serde_json::json;
use uuid::Uuid;

use super::labelling::{pending_observations, run_label_stage, LabelStage};
use super::relabel;
use crate::answers::answer_observations;
use crate::assessments::{self, NewAssessment};
use crate::engine::{scanned_objects, RoomInput, ScannedObject, SceneEngine};
use crate::findings::{needs_info_finding, summarize, EvaluationReport, Finding};
use crate::jobs::queue::{enqueue, EnqueueOptions, JobKind};
use crate::live::protocol::ServerMessage;
use crate::live::rooms::{load_rooms, save_room_observations, RoomState};
use crate::scans::models::{Report, StageTimings};
use crate::state::AppState;

fn elapsed_ms(since: Instant) -> u64 {
    since.elapsed().as_millis() as u64
}

/// Owner answers are scene-wide observations, so they ride along with the first room.
fn inputs_with_answers(rooms: &[RoomState], answers: Vec<serde_json::Value>) -> Vec<RoomInput> {
    let mut inputs: Vec<_> = rooms.iter().map(RoomState::to_input).collect();
    if let Some(first) = inputs.first_mut() {
        first.observations.extend(answers);
    }
    inputs
}

async fn evaluate_rooms(inputs: Vec<RoomInput>) -> Result<EvaluationReport> {
    tokio::task::spawn_blocking(move || {
        let mut engine = SceneEngine::new()?;
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

/// Findings the server adds to the engine's: unidentified crops and objects to ask the owner about.
fn labelling_findings(
    stage: &LabelStage,
    rooms: &[RoomState],
    answers: &[serde_json::Value],
    scanned: &BTreeMap<String, ScannedObject>,
) -> Vec<Finding> {
    let mut findings = unresolved_findings(stage);
    findings.extend(relabel::questions(rooms, answers, scanned));
    findings
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Labelling {
    Run,
    /// Re-assessments keep the labels saved at finish and don't call the vision API again.
    Reuse,
}

/// Labels come back on the in-memory rooms; save them so a later re-assessment keeps them.
async fn save_labels(state: &AppState, scan_id: Uuid, rooms: &[RoomState]) -> Result<()> {
    for room in rooms {
        save_room_observations(&state.db, scan_id, room).await?;
    }
    Ok(())
}

/// Detector crops and RoomPlan relabels go to the model side by side, under one deadline each.
async fn label_rooms(
    state: &AppState,
    scan_id: Uuid,
    rooms: &mut [RoomState],
    scanned: &BTreeMap<String, ScannedObject>,
    labelling: Labelling,
) -> Result<LabelStage> {
    if labelling == Labelling::Reuse {
        return Ok(LabelStage {
            labelled: 0,
            unresolved: pending_observations(rooms),
        });
    }
    let jobs = relabel::prepare(state, scan_id, rooms, scanned).await?;
    let (stage, relabels) = tokio::join!(
        run_label_stage(state, scan_id, rooms),
        relabel::fetch(state, scan_id, jobs)
    );
    let mut stage = stage?;
    let relabelled = relabel::apply(rooms, &relabels?);
    stage.labelled += relabelled.applied;
    if stage.labelled > 0 || relabelled.changed > 0 {
        save_labels(state, scan_id, rooms).await?;
    }
    Ok(stage)
}

pub async fn run_finish(state: &AppState, scan_id: Uuid) -> Result<Report> {
    assess(state, scan_id, Labelling::Run).await
}

/// Evaluate again with the latest owner answers, keeping the labels from finish.
pub async fn run_reassessment(state: &AppState, scan_id: Uuid) -> Result<Report> {
    assess(state, scan_id, Labelling::Reuse).await
}

async fn assess(state: &AppState, scan_id: Uuid, labelling: Labelling) -> Result<Report> {
    let total = Instant::now();

    let stage_start = Instant::now();
    let mut rooms = load_rooms(&state.db, scan_id).await?;
    let answers = answer_observations(&state.db, scan_id).await?;
    let inputs: Vec<RoomInput> = rooms.iter().map(RoomState::to_input).collect();
    let scanned = scanned_objects(&inputs);
    let load_ms = elapsed_ms(stage_start);

    let stage_start = Instant::now();
    let label_stage = label_rooms(state, scan_id, &mut rooms, &scanned, labelling).await?;
    let extra = labelling_findings(&label_stage, &rooms, &answers, &scanned);
    let labelling_ms = elapsed_ms(stage_start);

    let stage_start = Instant::now();
    let evaluation = evaluate_rooms(inputs_with_answers(&rooms, answers)).await?;
    let mut findings = evaluation.findings;
    findings.extend(extra);
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
    let inputs = inputs_with_answers(&rooms, answer_observations(db, scan_id).await?);
    tokio::task::spawn_blocking(move || crate::engine::assemble_scene(&inputs)).await?
}
