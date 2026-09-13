"""The measured model. Only ingest writes dimensions; no agent ever does."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .geometry import Mat4, Vec3

NodeKind = Literal["wall", "door", "window", "opening", "floor", "object"]

Quality = Literal["measured", "needs_another_look", "confirmed"]
"""measured: LiDAR at high confidence.
needs_another_look: thin coverage or low confidence; becomes a request, not a finding.
confirmed: a number a person entered by hand.
"""

LabelSource = Literal["roomplan", "astra", "owner", "discovery"]
"""discovery: found in the LiDAR and named from the photos, because RoomPlan boxes no such category."""


class DisplayAppearance(BaseModel):
    """An inferred finish for rendering; never physical or compliance evidence."""

    model_config = ConfigDict(extra="forbid")
    base_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    material: Literal["paint", "wood", "fabric", "metal", "stone", "glass", "neutral"]
    source: Literal["astra"] = "astra"


class DisplayPart(BaseModel):
    """A completed visual part inside the measured object's normalized bounds."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=60)
    primitive: Literal["box", "cylinder", "ellipsoid"]
    center: list[float] = Field(min_length=3, max_length=3)
    size: list[float] = Field(min_length=3, max_length=3)
    axis: Literal["x", "y", "z"] = "z"
    bevel: float = Field(default=0.02, ge=0, le=0.2)
    base_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    material: Literal["paint", "wood", "fabric", "metal", "stone", "glass", "neutral"]

    @model_validator(mode="after")
    def within_measured_bounds(self) -> DisplayPart:
        if any(size <= 0 or abs(center) + size / 2 > 0.50001 for center, size in zip(self.center, self.size)):
            raise ValueError("display parts must stay inside the measured object bounds")
        return self


class DisplayReconstruction(BaseModel):
    """Photo-informed completion. Never a recovered measurement or verified clearance."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    source: Literal["astra"] = "astra"
    summary: str = Field(min_length=1, max_length=300)
    confidence: float = Field(ge=0, le=1)
    evidence_frame_ids: list[str] = Field(min_length=1, max_length=6)
    parts: list[DisplayPart] = Field(min_length=1, max_length=32)


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
    appearance: DisplayAppearance | None = Field(default=None, exclude_if=lambda value: value is None)
    reconstruction: DisplayReconstruction | None = Field(default=None, exclude_if=lambda value: value is None)

    @property
    def touches_floor(self) -> bool:
        return self.kind in ("object", "door", "opening")


class SceneGraph(BaseModel):
    scan_id: UUID
    revision: int = 0
    base_hash: str | None = None
    nodes: list[SceneNode]
    capture_to_room: Mat4 | None = Field(default=None, exclude_if=lambda value: value is None)
    """ARKit world to this graph's room frame: the Y-up to Z-up turn, then the floor drop.

    Photos and the raw scan are posed in ARKit world, so projecting a photo onto
    the model maps model points back through the inverse of this.
    """

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
    anchor_node_id: UUID | None = None
    """The fixture this stop is at, such as the counter a customer orders from.

    Route width ignores only this node near the stop. A stop with no anchor gets
    no exemption, so an obstruction beside it still counts.
    """


class Scenario(BaseModel):
    """The routine we screen. Legs run between consecutive stops."""

    name: str = "Order a drink"
    stops: list[Stop] = Field(min_length=2)
