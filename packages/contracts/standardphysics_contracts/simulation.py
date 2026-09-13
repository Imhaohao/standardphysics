"""Bounded screening jobs against an immutable room and route snapshot."""
from __future__ import annotations

from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from .scene import SceneGraph


class RebuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=0)


class SimulationRequest(RebuildRequest):
    samples: int = Field(default=1000, ge=1, le=10000)
    max_workers: int = Field(default=4, ge=1, le=16)
    router: Literal["local", "typesafe"] = "local"
    refine_with_astra: bool = False


class SimulationFeedback(BaseModel):
    workflow_title: str
    profile_title: str
    trials: int
    passed_trials: int
    clearance_failure_trials: int
    floor_plan_collision_trials: int
    mesh_collision_trials: int
    unreachable_interaction_trials: int
    needs_measurement_trials: int
    blocking_node_ids: list[str]


class SimulationResult(BaseModel):
    total_runs: int
    completed_runs: int
    rejected_runs: int
    unique_layouts: int
    action_counts: dict[str, int]
    rejection_counts: dict[str, int]
    feedback: list[SimulationFeedback]
    recommended_graph: SceneGraph | None
    rules_checked: int
    rules_total: int
    preview: bool
    mesh_checked: bool
    redesign_model: str | None = None
    redesign_accepted: bool = False
    redesign_reasons: list[str] = []
    limitations: list[str]


class SimulationStatus(BaseModel):
    base_revision: int
    state: Literal["queued", "running", "done", "failed"]
    router: Literal["local", "typesafe"]
    samples: int
    completed: int
    error: str | None = None
    result: SimulationResult | None = None


class ReplayChapter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seconds: float = Field(ge=0, allow_inf_nan=False)
    task: str = Field(min_length=1)
    evaluation: int = Field(ge=1)
    outcome: Literal["route_blocked", "out_of_reach", "route_and_reach_fit"]


class SimulationReplay(BaseModel):
    """A saved functional campaign, separate from live legal screening jobs."""

    model_config = ConfigDict(extra="forbid")
    scan_id: UUID
    revision: int = Field(ge=0)
    graph_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    video_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluations: int = Field(ge=1)
    unique_layouts: int = Field(ge=1)
    connectivity_builds: int = Field(ge=1)
    typesafe_calls: int = Field(ge=0)
    task_source: str
    duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    selection: str
    chapters: list[ReplayChapter] = Field(min_length=1)
    limitations: list[str]
