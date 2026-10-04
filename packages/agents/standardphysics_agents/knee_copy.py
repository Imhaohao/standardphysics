"""The sentences a finding carries when its space reaches under a table, or needs a look under one.

A turning space or a clear floor space may count the knee and toe clearance
under a table or a counter. An owner reads the number against floor they can
see, so a finding whose space counted the floor under a piece names the piece:
they can check that floor and keep it clear. When the scan missed that floor
and it decides the answer, the finding asks them to show it to the phone.
"""

from __future__ import annotations

from dataclasses import replace

from .checks.observation import Observation
from .copy import FindingCopy
from .numbers import things


def with_counted_floor(copy: FindingCopy, observation: Observation) -> FindingCopy:
    """The copy, with a sentence naming the pieces whose floor the space counted, when it counted any."""
    labels = observation.facts.get("under") or []
    if not labels:
        return copy
    counted = (
        f"That counts the floor under {things(labels)}, "
        f"because a wheelchair user's feet and knees fit under {_them(labels)}."
    )
    keep = " Keep that floor clear." if observation.satisfied else ""
    return replace(copy, detail=f"{copy.detail} {counted}{keep}")


def look_underneath(labels: list[str]) -> FindingCopy:
    """Ask for another pass of the phone under the pieces whose floor the scan missed."""
    subject = things(labels) or "the table"
    return FindingCopy(
        title=f"Point the phone under {subject} again",
        detail=(
            f"Crouch a little so the phone sees the floor under {_them(labels)}. "
            "If that floor is clear, there's enough room here for a wheelchair."
        ),
    )


def _them(labels: list[str]) -> str:
    return "it" if len(labels) == 1 else "them"
