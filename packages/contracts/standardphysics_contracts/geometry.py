"""Units are meters and Z is up, everywhere behind the UI boundary.

RoomPlan hands back Y-up meters. The conversion happens once, on ingest, in
packages/pipeline/coords.py. Inches appear only at the display boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

METERS_PER_INCH = 0.0254


def to_inches(meters: float) -> float:
    return meters / METERS_PER_INCH


def to_meters(inches: float) -> float:
    return inches * METERS_PER_INCH


class Vec3(BaseModel):
    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


class Mat4(BaseModel):
    """Row-major 4x4 transform."""

    m: list[float] = Field(min_length=16, max_length=16)

    @classmethod
    def identity(cls) -> Mat4:
        return cls(m=[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])

    @classmethod
    def translation(cls, x: float, y: float, z: float) -> Mat4:
        return cls(m=[1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z, 0, 0, 0, 1])

    @property
    def position(self) -> Vec3:
        return Vec3(x=self.m[3], y=self.m[7], z=self.m[11])


class CameraPose(BaseModel):
    position: Vec3
    target: Vec3
    fov_degrees: float = 50.0
