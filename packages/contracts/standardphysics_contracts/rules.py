"""Rule packs hold thresholds in their original legal units, named by `unit`.

Conversion to a display string happens once, at the UI boundary. A rounded
label never changes an acceptance threshold.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Authority = Literal["ADA_2010", "CBC", "PAMC"]

Tier = Literal[1, 2, 3]


class Citation(BaseModel):
    authority: Authority
    edition: str
    section: str
    url: str | None = None

    def display(self) -> str:
        return f"{self.edition} {self.section}"


class Check(BaseModel):
    id: str
    title: str
    """Plain language, for the owner. "The path to the counter is too narrow"."""

    citation: Citation
    tier: Tier = 1
    threshold: float
    unit: str
    """The unit the standard is written in: "in" for a width, "lbf" for a door's
    opening force."""

    applies_to: list[str] = []
    verified_by_human: bool = False
    """No check may be enabled until a person has read the source section."""


class RulePack(BaseModel):
    version: str
    checks: list[Check]

    def enabled(self, max_tier: Tier = 1) -> list[Check]:
        return [c for c in self.checks if c.tier <= max_tier and c.verified_by_human]
