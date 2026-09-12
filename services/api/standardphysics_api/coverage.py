"""Lane A's coverage.json, read into the contract.

The app writes a dictionary keyed by RoomPlan element UUID. A list of
`SurfaceCoverage` is accepted too. Coverage never blocks a scan: an unreadable
file yields no coverage, and the scan carries on.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError
from standardphysics_contracts import SurfaceCoverage

log = logging.getLogger(__name__)


def _entries(payload) -> list[dict]:
    if isinstance(payload, dict):
        return [{"node_id": key, **value} for key, value in payload.items() if isinstance(value, dict)]
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, dict)]
    return []


def parse_coverage(raw: bytes) -> list[SurfaceCoverage]:
    try:
        return [SurfaceCoverage.model_validate(entry) for entry in _entries(json.loads(raw))]
    except (ValueError, ValidationError) as exc:
        log.warning("coverage.json unreadable, continuing without it: %s", exc)
        return []
