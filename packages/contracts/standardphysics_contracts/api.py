"""Request and response bodies the API adds around the domain models.

The upload shapes match `services/api/openapi.json`, which Lane A codes
against, and the mock server's error bodies.
"""

from __future__ import annotations

from pydantic import BaseModel

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
