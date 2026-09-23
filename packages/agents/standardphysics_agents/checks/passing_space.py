"""ADA 2010 403.5.3. Whether two people can get past each other.

The section only bites on routes narrower than 60 inches, and it is satisfied
by a 60 inch square anywhere along the route at 200 foot intervals. A shop is
far shorter than one interval, so in practice one square is enough, and the
interval arithmetic is here so that stays true rather than assumed.
"""

from __future__ import annotations

import math

from standardphysics_contracts import ClearFloorResult, Vec3, WidthResult
from standardphysics_pipeline import path_locus, region_locus

from ..rules import RuleSpec
from ..tracing import traced
from .clear_floor import fits_square, square_side
from .context import CheckContext
from .observation import Observation
from .route_geometry import route_length_feet, sample_path

RULE_ID = "passing_space"

SAMPLE_SPACING_METERS = 0.5
"""Close enough to catch the open middle of a room, coarse enough to be quick."""


@traced("checks.passing_space")
def passing_space(ctx: CheckContext) -> list[Observation]:
    rule = ctx.rule(RULE_ID)
    legs = [ctx.measure.route_clear_width(ctx.graph, ctx.scenario, i) for i in ctx.legs()]
    reachable = [leg for leg in legs if leg.reachable]
    if not reachable:
        return []

    narrowest = min(reachable, key=lambda leg: leg.inches)
    if narrowest.inches >= rule.parameter("applies_below_route_width_inches"):
        return [_not_required(rule, narrowest)]

    spaces = _spaces_along(ctx, rule, reachable)
    needed = _spaces_needed(route_length_feet(reachable), rule)
    return [_verdict(rule, narrowest, spaces, needed)]


def _not_required(rule: RuleSpec, narrowest: WidthResult) -> Observation:
    return Observation(
        rule_id=RULE_ID,
        satisfied=True,
        measured_inches=narrowest.inches,
        required_inches=rule.threshold,
        locus=path_locus(narrowest),
        facts={"applies": False},
        dedupe_key=(RULE_ID,),
        reason="route_wide_enough",
    )


def _verdict(
    rule: RuleSpec,
    narrowest: WidthResult,
    spaces: list[ClearFloorResult],
    needed: int,
) -> Observation:
    best = max(spaces, key=square_side, default=None)
    satisfied = len(spaces) >= needed
    return Observation(
        rule_id=RULE_ID,
        satisfied=satisfied,
        measured_inches=square_side(best) if best else 0.0,
        required_inches=rule.parameter("space_min_inches"),
        relied_on=tuple(narrowest.blocking_node_ids),
        locus=(
            region_locus(best, list(narrowest.blocking_node_ids))
            if best
            else path_locus(narrowest)
        ),
        facts={
            "applies": True,
            "route_width": narrowest.inches,
            "spaces_found": len(spaces),
            "spaces_needed": needed,
        },
        dedupe_key=(RULE_ID,),
        reason="has_passing_space" if satisfied else "no_passing_space",
    )


def _spaces_needed(route_feet: float, rule: RuleSpec) -> int:
    interval = rule.parameter("interval_max_feet")
    return max(1, math.ceil(route_feet / interval))


def _spaces_along(
    ctx: CheckContext, rule: RuleSpec, legs: list[WidthResult]
) -> list[ClearFloorResult]:
    minimum = rule.parameter("space_min_inches")
    return [
        space
        for point, heading in _sample_points(legs)
        if fits_square(space := _square_at(ctx, point, heading), minimum)
    ]


def _square_at(ctx: CheckContext, point: Vec3, heading: tuple[float, float]) -> ClearFloorResult:
    """The clear square at a point on the route, turned to the route.

    A provider that cannot measure a square is asked for its clear circle, the
    reading this check used before providers could. A 60 inch circle does not
    hold a 60 inch square, so that reading passes spaces that are too small.
    """
    measure_square = getattr(ctx.measure, "largest_square", None)
    if measure_square is None:
        return ctx.measure.turning_space(ctx.graph, point)
    return measure_square(ctx.graph, point, heading)


def _sample_points(legs: list[WidthResult]) -> list[tuple[Vec3, tuple[float, float]]]:
    """Points along each leg, with the direction the route runs there."""
    samples: list[tuple[Vec3, tuple[float, float]]] = []
    for leg in legs:
        points = sample_path(leg.path, SAMPLE_SPACING_METERS)
        for index, point in enumerate(points):
            ahead = points[min(index + 1, len(points) - 1)]
            behind = points[max(index - 1, 0)]
            samples.append((point, _heading(behind, ahead)))
    return samples


def _heading(behind: Vec3, ahead: Vec3) -> tuple[float, float]:
    dx, dy = ahead.x - behind.x, ahead.y - behind.y
    length = math.hypot(dx, dy)
    return (1.0, 0.0) if length < 1e-9 else (dx / length, dy / length)
