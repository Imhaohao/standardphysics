from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from .findings import Finding
from .geometry import Vec3

RouterAction = Literal["FIX", "RESCAN_AREA", "ASK_OWNER", "ESCALATE", "DONE"]


class Decision(BaseModel):
    """TypeSafe's structured output, after validation.

    An action that fails validation authorizes nothing.
    """

    action: RouterAction
    target_finding_ids: list[UUID] = []
    question: str | None = None
    rationale: str | None = None
    provider: str = "typesafe"


class NodeMove(BaseModel):
    node_id: UUID
    delta_translation: Vec3
    delta_rotation_z_degrees: float = 0.0


class Proposal(BaseModel):
    """Movable nodes only. No resize, no fixture movement, no leaving the floor."""

    id: UUID
    base_graph_hash: str
    moves: list[NodeMove]
    targets: list[UUID]
    rationale: str
    inventory_before: dict[str, int] = {}
    inventory_after: dict[str, int] = {}

    @property
    def preserves_inventory(self) -> bool:
        return self.inventory_before == self.inventory_after


class Assessment(BaseModel):
    id: UUID
    scan_id: UUID
    graph_revision: int
    graph_hash: str
    rulepack_version: str
    pass_number: int
    created_at: datetime
    findings: list[Finding]
    decision: Decision | None = None
    weave_run_url: str | None = None
    rules_checked: int | None = None
    """How many rules a person had verified when this ran. Zero means nothing was checked."""

    @property
    def problems(self) -> list[Finding]:
        return [f for f in self.findings if f.outcome == "problem"]

    @property
    def questions(self) -> list[Finding]:
        return [f for f in self.findings if f.outcome == "question"]
