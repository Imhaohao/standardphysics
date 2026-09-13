"""Persisted, bounded room screening on the existing background worker."""
from __future__ import annotations

import os
from uuid import UUID

from standardphysics_agents import load_pack
from standardphysics_agents.simulation_report import simulation_result
from standardphysics_agents.redesign import propose_redesign
from standardphysics_agents.mesh_collision import MeshCollisionIndex
from standardphysics_agents.router import LocalPolicyRouter, TypeSafeRouter
from standardphysics_agents.workflows import (
    DEFAULT_PROFILES, Interaction, build_workflow_suite, run_workflow_batch,
)
from standardphysics_contracts import (
    LidarMesh, Scenario, SceneGraph, SimulationRequest,
    SimulationResult, SimulationStatus,
)
from standardphysics_pipeline import PipelineMeasurements

from . import repository as repo
from .errors import ApiProblem

SIMULATE = "simulate"


def _live_ready(stages) -> None:
    router = TypeSafeRouter()
    if not router.configured:
        raise ApiProblem(409, "TypeSafe is not configured; set TYPESAFE_API_KEY on the server")
    ledger = stages.ledger_factory()
    enabled = load_pack().enabled(ledger, max_tier=3)
    if not enabled or any("unverified preview" in ledger.entry_for(rule).verified_by for rule in enabled):
        raise ApiProblem(409, "Live screening requires human-verified rules; preview rules cannot certify a room")


def queue_simulation(database, stages, worker, scan_id: UUID, body: SimulationRequest) -> SimulationStatus:
    if body.router == "typesafe":
        _live_ready(stages)
    if body.refine_with_astra and not os.environ.get("OPENROUTER_API_KEY"):
        raise ApiProblem(409, "Astra needs OPENROUTER_API_KEY on the server")
    with database.transaction() as connection:
        if not repo.scan_exists(connection, scan_id):
            raise ApiProblem(404, "no scan")
        latest = repo.get_revision(connection, scan_id)
        scenario = repo.get_scenario(connection, scan_id)
        if latest is None or scenario is None:
            raise ApiProblem(409, "Confirm a customer route before running simulations")
        if latest["revision"] != body.base_revision:
            raise ApiProblem(409, "a newer layout was saved since this one started")
        active = connection.execute(
            "SELECT 1 FROM jobs WHERE scan_id = ? AND kind = ? AND state IN ('queued', 'running')",
            (str(scan_id), SIMULATE),
        ).fetchone()
        if active:
            raise ApiProblem(409, "a simulation for this room is already queued or running")
        mesh = repo.artifact_of_kind(connection, scan_id, "lidar_mesh")
        connection.execute(
            "INSERT INTO simulations (scan_id, revision, request_json, graph_json, scenario_json, mesh_artifact_id)"
            " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(scan_id, revision) DO UPDATE SET"
            " request_json=excluded.request_json, graph_json=excluded.graph_json, scenario_json=excluded.scenario_json,"
            " mesh_artifact_id=excluded.mesh_artifact_id, completed=0, result_json=NULL",
            (str(scan_id), body.base_revision, body.model_dump_json(), latest["graph_json"],
             scenario.model_dump_json(), mesh.id if mesh else None),
        )
        repo.queue_job_again(connection, scan_id, SIMULATE, body.base_revision)
    worker.wake()
    return simulation_status(database, scan_id, body.base_revision)


def simulation_status(database, scan_id: UUID, revision: int) -> SimulationStatus:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT s.*, j.state, j.error FROM simulations s JOIN jobs j"
            " ON s.scan_id=j.scan_id AND s.revision=j.revision AND j.kind=?"
            " WHERE s.scan_id=? AND s.revision=?",
            (SIMULATE, str(scan_id), revision),
        ).fetchone()
    if row is None:
        raise ApiProblem(404, "no simulation for this revision")
    request = SimulationRequest.model_validate_json(row["request_json"])
    return SimulationStatus(
        base_revision=revision, state=row["state"], router=request.router,
        samples=request.samples, completed=row["completed"], error=row["error"],
        result=SimulationResult.model_validate_json(row["result_json"]) if row["result_json"] else None,
    )


def _interactions(graph: SceneGraph, scenario: Scenario) -> list[Interaction]:
    nodes = {node.id: node for node in graph.nodes if node.kind == "object"}
    targets = dict.fromkeys(stop.anchor_node_id for stop in scenario.stops if stop.anchor_node_id in nodes)
    return [Interaction(id=str(key), title=f"Reach {nodes[key].label}", target_node_id=key, height="top")
            for key in targets]


def run_simulation(database, store, stages, scan_id: UUID, revision: int) -> None:
    with database.connect() as connection:
        row = connection.execute("SELECT * FROM simulations WHERE scan_id=? AND revision=?", (str(scan_id), revision)).fetchone()
    request = SimulationRequest.model_validate_json(row["request_json"])
    if request.router == "typesafe":
        _live_ready(stages)
    graph = SceneGraph.model_validate_json(row["graph_json"])
    scenario = Scenario.model_validate_json(row["scenario_json"])
    mesh = (LidarMesh.model_validate_json(store.artifact_path(scan_id, row["mesh_artifact_id"]).read_bytes())
            if row["mesh_artifact_id"] else None)
    ledger = stages.ledger_factory()
    rules = load_pack()

    def progress(completed: int) -> None:
        if completed % 10 == 0 or completed == request.samples:
            with database.transaction() as connection:
                connection.execute("UPDATE simulations SET completed=? WHERE scan_id=? AND revision=?", (completed, str(scan_id), revision))

    workflows = build_workflow_suite(graph, scenario, interactions=_interactions(graph, scenario))
    batch = run_workflow_batch(
        graph, workflows=workflows,
        profiles=list(DEFAULT_PROFILES), samples=request.samples, max_workers=request.max_workers,
        measure_factory=PipelineMeasurements,
        router_factory=TypeSafeRouter if request.router == "typesafe" else LocalPolicyRouter,
        rules=rules, ledger=ledger, lidar_mesh=mesh, on_progress=progress,
    )
    result = simulation_result(batch, rules, ledger, mesh)
    if request.refine_with_astra:
        redesign = propose_redesign(
            result.recommended_graph or graph, workflows, list(DEFAULT_PROFILES),
            [item.model_dump(mode="json") for item in result.feedback], PipelineMeasurements(),
            rules=rules, ledger=ledger, collision_index=MeshCollisionIndex(mesh) if mesh else None,
        )
        result = result.model_copy(update={
            "recommended_graph": redesign.graph or result.recommended_graph,
            "redesign_model": redesign.model, "redesign_accepted": redesign.accepted,
            "redesign_reasons": list(redesign.reasons),
        })
    with database.transaction() as connection:
        connection.execute("UPDATE simulations SET result_json=?, completed=? WHERE scan_id=? AND revision=?", (result.model_dump_json(), request.samples, str(scan_id), revision))
