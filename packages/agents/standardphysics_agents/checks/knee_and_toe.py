"""Knee and toe clearance, counted only where ADA 2010 allows it.

304.3.1 lets a turning space include knee and toe clearance complying with
306, 603.2.1 asks a toilet room for turning space complying with 304, and
305.4 lets a clear floor space include it as well. Nothing else may: a route's
clear width, a passing space and a door's maneuvering clearance are measured on
the plain grid, and their checks never come here.

A check asks its plain question first and counts the space under a piece only
when the plain answer falls short, so a space that fits without it never leans
on it. When it does lean on it, the finding names the piece, so the owner
knows the floor under it has to stay clear. When the scan missed the floor
under a piece and seeing it clear would change the answer, the finding asks
for another look instead of passing on floor nobody saw.

306's numbers sit with the turning space rule, whose own text grants the
credit; the restroom and the counter read the same ones.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from standardphysics_contracts import ClearFloorResult, Vec3, to_meters
from standardphysics_contracts.findings import Asks
from standardphysics_pipeline.knee_and_toe import KneeAndToeLimits, KneeAndToeSpace

from .clear_floor import square_side
from .context import CheckContext

GRANTING_RULE = "turning_space"
"""The rule whose text grants the credit, and so the one holding 306's numbers."""

Fits = Callable[[ClearFloorResult], bool]
Plain = Callable[[Vec3], ClearFloorResult]
Counting = Callable[[Vec3], KneeAndToeSpace]


def limits(ctx: CheckContext) -> KneeAndToeLimits:
    """306's numbers, in metres, from the rule pack."""
    rule = ctx.rule(GRANTING_RULE)

    def metres(name: str) -> float:
        return to_meters(rule.parameter(name))

    return KneeAndToeLimits(
        toe_top=metres("toe_clearance_top_inches"),
        toe_deepest=metres("toe_clearance_depth_max_inches"),
        toe_past_knee=metres("toe_clearance_past_knee_max_inches"),
        knee_top=metres("knee_clearance_top_inches"),
        knee_deepest=metres("knee_clearance_depth_max_inches"),
        knee_reduction=rule.parameter("knee_clearance_reduction_depth_inches")
        / rule.parameter("knee_clearance_reduction_height_inches"),
        narrowest=max(metres("toe_clearance_width_min_inches"), metres("knee_clearance_width_min_inches")),
    )


def turning_counted(ctx: CheckContext) -> Counting | None:
    """The provider's turning space counting knee and toe clearance, or None from a provider that cannot.

    Without it a check answers on the plain grid alone, which can only ever
    find less room, never more.
    """
    measure = getattr(ctx.measure, "turning_space_with_knee_and_toe", None)
    if measure is None:
        return None
    allowed = limits(ctx)
    return lambda at: measure(ctx.graph, at, allowed)


def approach_counted(ctx: CheckContext, counter_id: UUID, slide_meters: float) -> Callable[[], KneeAndToeSpace] | None:
    """The provider's clear floor in front of a counter counting knee and toe clearance, or None."""
    measure = getattr(ctx.measure, "counter_approach_with_knee_and_toe", None)
    if measure is None:
        return None
    allowed = limits(ctx)
    return lambda: measure(ctx.graph, counter_id, slide_meters, allowed)


@dataclass(frozen=True)
class Settled:
    """The clear space a check reports, where it sits, and the knee and toe clearance behind it."""

    space: ClearFloorResult
    at: Vec3
    under: tuple[UUID, ...] = ()
    """Pieces whose knee and toe clearance the space counts."""
    look_under: tuple[UUID, ...] = ()
    """Pieces whose unseen floor would give the space room enough, were it clear."""

    @property
    def asks_for(self) -> Asks | None:
        return "another_look" if self.look_under else None

    @property
    def pieces(self) -> tuple[UUID, ...]:
        """Every piece the answer rests on beyond the plain grid."""
        return (*self.under, *self.look_under)

    def facts(self, ctx: CheckContext) -> dict[str, Any]:
        """What the copy needs to name the pieces."""
        return {
            "under": [ctx.label(node_id) for node_id in self.under],
            "look_under": [ctx.label(node_id) for node_id in self.look_under],
        }


def first_fit(candidates: list[Vec3], plain: Plain, counting: Counting | None, fits: Fits) -> Settled:
    """The first candidate with room on the plain grid, else the first with room counting knee and toe clearance.

    Failing both, the first that the unseen floor under a piece could settle,
    and failing that, the first candidate as the scan shows it.
    """
    for at in candidates:
        space = plain(at)
        if fits(space):
            return Settled(space, at)
    if counting is None:
        return Settled(plain(candidates[0]), candidates[0])
    counted = [(at, counting(at)) for at in candidates]
    return _settle(counted, fits)


def widest(candidates: list[Vec3], plain: Plain, counting: Counting | None, fits: Fits) -> Settled | None:
    """The widest candidate on the plain grid, or, when it falls short, the widest counting knee and toe clearance."""
    if not candidates:
        return None
    space, at = max(((plain(at), at) for at in candidates), key=lambda pair: square_side(pair[0]))
    if fits(space) or counting is None:
        return Settled(space, at)
    counted = sorted(((at, counting(at)) for at in candidates), key=lambda pair: -square_side(pair[1].space))
    return _settle(counted, fits)


def settle_one(plain: ClearFloorResult, counting: Callable[[], KneeAndToeSpace] | None, fits: Fits) -> Settled:
    """One space, counting knee and toe clearance only when it falls short without."""
    if fits(plain) or counting is None:
        return Settled(plain, plain.center)
    counted = counting()
    return _settle([(counted.space.center, counted)], fits)


def _settle(counted: list[tuple[Vec3, KneeAndToeSpace]], fits: Fits) -> Settled:
    """The first that fits counting what the scan shows, else the first unseen floor could settle, else the first."""
    for at, measured in counted:
        if fits(measured.space):
            return Settled(measured.space, at, under=measured.under)
    for at, measured in counted:
        if measured.if_seen is not None and fits(measured.if_seen):
            return Settled(measured.space, at, look_under=measured.unseen_under)
    at, measured = counted[0]
    return Settled(measured.space, at, under=measured.under)
