"""Strict validation for uploaded raw AR mesh JSON."""

from __future__ import annotations

import json

from pydantic import ValidationError
from standardphysics_contracts import LidarMesh


class InvalidLidarMesh(ValueError):
    pass


def validate_lidar_mesh(payload: bytes) -> LidarMesh:
    try:
        document = json.loads(payload)
        return LidarMesh.model_validate(document)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValidationError) as error:
        raise InvalidLidarMesh("invalid lidar mesh") from error
