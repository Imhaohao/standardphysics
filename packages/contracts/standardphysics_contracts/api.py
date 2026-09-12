"""Request and response bodies the API adds around the domain models.

The upload shapes match `services/api/openapi.json`, which Lane A codes
against, and the mock server's error bodies.
"""

from __future__ import annotations

from pydantic import BaseModel

from .findings import Finding
from .loop import NodeMove
from .scan import Scan


class CreateScanRequest(BaseModel):
    name: str
    device_model: str
    duration_seconds: float


class ScanList(BaseModel):
    scans: list[Scan]


class ApiError(BaseModel):
    error: str
    need: list[str] | None = None


class Blocked(BaseModel):
    """A hard constraint a layout breaks, from Lane C's fix constraints."""

    node_id: str
    reason: str
    """moved_something_fixed, resized, inventory_changed, left_the_floor, collided or blocked_a_door."""
    detail: str


class LayoutCheckRequest(BaseModel):
    """Every move so far against one saved revision, never just the latest drag.

    `sequence` rises with each drop, so the client can ignore an answer that
    arrives after a newer one.
    """

    base_revision: int
    sequence: int
    moves: list[NodeMove]


class LayoutCheckResult(BaseModel):
    sequence: int
    graph_hash: str
    findings: list[Finding]
    blocked: list[Blocked]


class SaveLayoutRequest(BaseModel):
    base_revision: int
    moves: list[NodeMove]
