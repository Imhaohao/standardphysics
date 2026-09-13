"""Persisted, bounded room screening on the existing background worker."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from standardphysics_agents import (
    TypeSafeCallBudget,
    analyze_environment_physics,
    load_pack,
    run_adaptive_redesign,
)
from standardphysics_agents.evaluation.scan_campaign import run_campaign
from standardphysics_agents.evaluation.scan_tasks import choose_task, propose_tasks
from standardphysics_agents.mesh_collision import MeshCollisionIndex
from standardphysics_agents.router import LocalPolicyRouter, TypeSafeRouter
from standardphysics_agents.simulation_report import simulation_result
from standardphysics_agents.workflows import (
    DEFAULT_PROFILES,
    Interaction,
    build_workflow_suite,
    run_workflow_batch,
)
from standardphysics_contracts import (
    LidarMesh,
    Scenario,
    SceneGraph,
    SimulationRequest,
    SimulationResult,
    SimulationStatus,
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
    if body.router == "typesafe" or body.refine_with_astra or body.exhaustive_evaluations:
        _live_ready(stages)
    if (body.refine_with_astra or body.exhaustive_evaluations) and not os.environ.get("OPENROUTER_API_KEY"):
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
        samples=request.samples, completed=row["completed"],
        typesafe_call_limit=request.typesafe_call_limit,
        exhaustive_evaluations=request.exhaustive_evaluations,
        error=row["error"],
        result=SimulationResult.model_validate_json(row["result_json"]) if row["result_json"] else None,
    )


def _interactions(graph: SceneGraph, scenario: Scenario) -> list[Interaction]:
    nodes = {node.id: node for node in graph.nodes if node.kind == "object"}
    targets = dict.fromkeys(stop.anchor_node_id for stop in scenario.stops if stop.anchor_node_id in nodes)
    return [Interaction(id=str(key), title=f"Reach {nodes[key].label}", target_node_id=key, height="top")
            for key in targets]


def run_simulation(database, store, stages, scan_id: UUID, revision: int) -> None:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT * FROM simulations WHERE scan_id=? AND revision=?",
            (str(scan_id), revision),
        ).fetchone()
    request = SimulationRequest.model_validate_json(row["request_json"])
    if request.router == "typesafe" or request.refine_with_astra or request.exhaustive_evaluations:
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
                connection.execute(
                    "UPDATE simulations SET completed=? WHERE scan_id=? AND revision=?",
                    (completed, str(scan_id), revision),
                )

    workflows = build_workflow_suite(graph, scenario, interactions=_interactions(graph, scenario))
    campaign_reserve = 9 if request.exhaustive_evaluations else 0
    adaptive_reserve = request.astra_rounds if request.refine_with_astra else 0
    workflow_budget = (
        TypeSafeCallBudget(
            request.typesafe_call_limit - campaign_reserve - adaptive_reserve
        )
        if request.router == "typesafe"
        else None
    )
    batch = run_workflow_batch(
        graph, workflows=workflows,
        profiles=list(DEFAULT_PROFILES), samples=request.samples, max_workers=request.max_workers,
        measure_factory=PipelineMeasurements,
        router_factory=(
            (lambda: TypeSafeRouter(budget=workflow_budget))
            if workflow_budget is not None
            else LocalPolicyRouter
        ),
        rules=rules, ledger=ledger, lidar_mesh=mesh, on_progress=progress,
    )
    result = simulation_result(batch, rules, ledger, mesh)
    typesafe_calls = workflow_budget.used if workflow_budget is not None else 0
    astra_calls = 0
    limitations = list(result.limitations)
    physics = analyze_environment_physics(
        graph, scenario, PipelineMeasurements(), mesh=mesh
    )

    exhaustive_count = 0
    exhaustive_outcomes: dict[str, int] = {}
    if request.exhaustive_evaluations:
        campaign_budget = TypeSafeCallBudget(campaign_reserve)
        campaign_path = (
            store.scan_dir(scan_id)
            / "revisions"
            / str(revision)
            / "deep_scan_campaign.json"
        )
        try:
            _validate_exhaustive_inputs(graph, mesh)
            astra_calls += 1
            campaign = _run_exhaustive_campaign(
                graph,
                mesh,
                request.exhaustive_evaluations,
                campaign_path,
                campaign_budget,
            )
            exhaustive_count = campaign["evaluations"]
            exhaustive_outcomes = campaign["outcomes"]
        except (RuntimeError, ValueError) as error:
            limitations.append(
                "Exhaustive route-and-reach campaign skipped: "
                f"{type(error).__name__}: {error}"
            )
        typesafe_calls += campaign_budget.used

    if request.refine_with_astra:
        adaptive_budget = TypeSafeCallBudget(adaptive_reserve)
        redesign = run_adaptive_redesign(
            graph,
            starting_graph=result.recommended_graph or graph,
            workflows=workflows,
            profiles=list(DEFAULT_PROFILES),
            measure=PipelineMeasurements(),
            rules=rules,
            ledger=ledger,
            rounds=request.astra_rounds,
            budget=adaptive_budget,
            collision_index=MeshCollisionIndex(mesh) if mesh else None,
        )
        last_round = redesign.rounds[-1] if redesign.rounds else None
        accepted_round = next(
            (item for item in reversed(redesign.rounds) if item.accepted), None
        )
        result = result.model_copy(update={
            "recommended_graph": redesign.graph or result.recommended_graph,
            "redesign_model": (
                accepted_round.astra_model
                if accepted_round is not None
                else last_round.astra_model if last_round else None
            ),
            "redesign_accepted": redesign.graph is not None,
            "redesign_reasons": (
                []
                if redesign.graph is not None
                else list(last_round.reasons) if last_round else []
            ),
            "adaptive_rounds": list(redesign.rounds),
        })
        astra_calls += redesign.astra_calls
        typesafe_calls += adaptive_budget.used

    if typesafe_calls > request.typesafe_call_limit:
        raise AssertionError("TypeSafe per-scan call limit was exceeded")
    if graph != SceneGraph.model_validate_json(row["graph_json"]):
        raise AssertionError("simulation changed its measured scan snapshot")
    result = result.model_copy(
        update={
            "typesafe_calls": typesafe_calls,
            "astra_calls": astra_calls,
            "physics": physics,
            "exhaustive_evaluations": exhaustive_count,
            "exhaustive_outcomes": exhaustive_outcomes,
            "limitations": limitations,
        }
    )
    with database.transaction() as connection:
        connection.execute(
            "UPDATE simulations SET result_json=?, completed=?"
            " WHERE scan_id=? AND revision=?",
            (result.model_dump_json(), request.samples, str(scan_id), revision),
        )


def _run_exhaustive_campaign(
    graph: SceneGraph,
    mesh: LidarMesh | None,
    evaluations: int,
    output: Path,
    budget: TypeSafeCallBudget,
) -> dict:
    _validate_exhaustive_inputs(graph, mesh)
    assert mesh is not None
    suite, source = propose_tasks(graph)
    router = TypeSafeRouter(budget=budget)
    campaign = run_campaign(
        graph,
        mesh,
        suite,
        evaluations=evaluations,
        seed=graph.revision + 20_260_913,
        output=output,
        planner=lambda tasks, history: choose_task(tasks, history, router),
    )
    campaign["task_generation"] = source
    return campaign


def _validate_exhaustive_inputs(
    graph: SceneGraph, mesh: LidarMesh | None
) -> None:
    if mesh is None:
        raise ValueError("a LiDAR mesh is required")
    if mesh.floorY is None:
        raise ValueError("the LiDAR mesh has no floor reference")
    if not any(
        node.kind == "object" and node.raw_category == "table"
        for node in graph.nodes
    ):
        raise ValueError("the scan has no table candidates for generated tasks")
