"""OpenRouter proposes room edits; measured constraints decide whether to keep them."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from standardphysics_contracts import NodeMove, SceneGraph, Vec3

from .assess import assess
from .evaluation.gate import accepts
from .fix import apply_moves, violations
from .models import ModelAnswer, OpenRouter
from .router import Rejected
from .workflows import workflow_candidate_rejection


class FurnitureMove(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    node_id: UUID
    dx: float = Field(ge=-20, le=20)
    dy: float = Field(ge=-20, le=20)
    rotation_degrees: float = Field(ge=-180, le=180)


class RoomEdits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    moves: list[FurnitureMove] = Field(max_length=64)


@dataclass(frozen=True)
class RedesignResult:
    graph: SceneGraph | None
    model: str | None
    accepted: bool
    reasons: tuple[str, ...]


INSTRUCTION = (
    "Propose a furniture arrangement that improves the measured accessibility issues in this room. "
    "Return floor translations in meters and rotations in degrees for existing movable object IDs only. "
    "Preserve every object's measured size, inventory, fixed fixtures, walls and doors. "
    "Do not infer that an attractive rendering is legally compliant. Return no moves if the measured "
    "evidence does not support a safe improvement. The application remeasures every route before accepting edits."
)


def propose_redesign(graph, workflows, profiles, feedback, measure, *, rules, ledger, model=None, collision_index=None) -> RedesignResult:
    client = model or OpenRouter()
    answer = client.structured(INSTRUCTION, {
        "room": graph.model_dump(mode="json"),
        "workflow_feedback": feedback,
        "verified_rules": [rule.model_dump(mode="json") for rule in rules.enabled(ledger, max_tier=3)],
    }, RoomEdits.model_json_schema(), "room_furniture_edits")
    if isinstance(answer, Rejected):
        return RedesignResult(None, client.model, False, (answer.reason,))
    return validate_redesign(graph, answer, workflows, profiles, measure, rules=rules, ledger=ledger, collision_index=collision_index)


def validate_redesign(graph, answer: ModelAnswer, workflows, profiles, measure, *, rules, ledger, collision_index=None) -> RedesignResult:
    try:
        edits = RoomEdits.model_validate(answer.payload)
    except ValidationError:
        return RedesignResult(None, answer.model, False, ("invalid_model_edits",))
    ids = [edit.node_id for edit in edits.moves]
    known = {node.id for node in graph.nodes}
    if not ids or len(ids) != len(set(ids)) or not set(ids) <= known:
        return RedesignResult(None, answer.model, False, ("empty_duplicate_or_unknown_objects",))
    moves = [NodeMove(node_id=edit.node_id, delta_translation=Vec3(x=edit.dx, y=edit.dy, z=0), delta_rotation_z_degrees=edit.rotation_degrees) for edit in edits.moves]
    candidate = apply_moves(graph, moves)
    broken = violations(graph, candidate)
    if broken:
        return RedesignResult(None, answer.model, False, tuple(sorted({item.kind for item in broken})))
    if not rules.enabled(ledger, max_tier=3):
        return RedesignResult(None, answer.model, False, ("no_verified_rules",))
    improved = False
    for workflow in workflows:
        before = assess(graph, workflow.scenario, measure, rules=rules, ledger=ledger, max_tier=3)
        after = assess(candidate, workflow.scenario, measure, rules=rules, ledger=ledger, max_tier=3)
        gate = accepts(before, after, require_improvement=False)
        if not gate:
            return RedesignResult(None, answer.model, False, gate.reasons)
        improved = improved or bool(accepts(before, after))
    regression = workflow_candidate_rejection(graph, candidate, workflows=workflows, profiles=profiles, measure=measure, collision_index=collision_index)
    if regression or not improved:
        return RedesignResult(None, answer.model, False, (regression or "nothing_measurable_improved",))
    return RedesignResult(candidate, answer.model, True, ())
