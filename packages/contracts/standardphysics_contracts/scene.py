"""The measured model. Only ingest writes dimensions; no agent ever does."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .geometry import Mat4, Vec3

NodeKind = Literal["wall", "door", "window", "opening", "floor", "object"]

Quality = Literal["measured", "needs_another_look", "confirmed"]
"""measured: LiDAR at high confidence.
needs_another_look: thin coverage or low confidence; becomes a request, not a finding.
confirmed: a number a person entered by hand.
"""

LabelSource = Literal["roomplan", "astra", "owner"]


class SceneNode(BaseModel):
    id: UUID
    kind: NodeKind
    label: str
    raw_category: str
    dimensions: Vec3
    transform: Mat4
    quality: Quality = "measured"
    movable: bool = False
    labeled_by: LabelSource = "roomplan"
    parent_id: UUID | None = None

    @property
    def touches_floor(self) -> bool:
        return self.kind in ("object", "door", "opening")


class SceneGraph(BaseModel):
    scan_id: UUID
    revision: int = 0
    base_hash: str | None = None
    nodes: list[SceneNode]

    def by_id(self, node_id: UUID) -> SceneNode:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    def movable(self) -> list[SceneNode]:
        return [n for n in self.nodes if n.movable]

    def obstacles(self) -> list[SceneNode]:
        return [n for n in self.nodes if n.touches_floor or n.kind == "wall"]


class Stop(BaseModel):
    """A destination on a customer's route."""

    name: str
    position: Vec3


class Scenario(BaseModel):
    """The routine we screen. Legs run between consecutive stops."""

    name: str = "Order a drink"
    stops: list[Stop] = Field(min_length=2)
