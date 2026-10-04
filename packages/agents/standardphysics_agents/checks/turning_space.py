"""ADA 2010 304.3. Room to turn around in a restroom or a fitting room.

304 is scoped by the sections that call for it rather than applying everywhere,
so this runs only at stops in a room whose own section asks for a turning
space. A dead end at a pickup counter or a row of seats is not one: a customer
there backs out, and reporting it would put a card in front of the owner that
no section backs.

304.3.1 fixes the circle's size, not where its centre sits. The circle is
first tried at the stop backed off by a clear-floor depth, the spot a
customer arriving head-on turns in. A customer who reaches a counter moving
along it, as at a pickup point, stands beside the counter with that spot
still beside the counter, so the fixed spot would fail every such counter
however the room is laid out. When it fails, any centre within one radius of
the stop counts. The stop is then inside the circle, and because the whole
circle has to be clear, so is the way from the stop to the centre.

304.3.1 also lets the circle include knee and toe clearance complying with 306.
That is counted only when no circle near the stop fits on the plain grid; see
`knee_and_toe`.
"""

from __future__ import annotations

import math
from uuid import UUID

from standardphysics_contracts import Vec3, to_meters
from standardphysics_pipeline import region_locus

from ..rules import RuleSpec
from ..tracing import traced
from .clear_floor import fits_turning_circle, square_side
from .context import CheckContext
from .knee_and_toe import Settled, first_fit, turning_counted
from .observation import Observation
from .rectangles import intruders, rectangle
from .route_geometry import setback_point, stops_needing_turning_space

RULE_ID = "turning_space"

APPROACH_SETBACK_INCHES = 30.0
"""The depth of a clear floor space, ADA 2010 305.3."""

SEARCH_STEP_INCHES = 6.0
"""Spacing of the candidate centres tried around the stop."""


@traced("checks.turning_space")
def turning_space(ctx: CheckContext) -> list[Observation]:
    rule = ctx.rule(RULE_ID)
    stops = ctx.scenario.stops
    return [_at_stop(ctx, rule, index) for index in stops_needing_turning_space(stops)]


def _centres_near(stop: Vec3, radius: float) -> list[Vec3]:
    """Lattice points within one radius of the stop, nearest first."""
    step = to_meters(SEARCH_STEP_INCHES)
    reach = int(radius // step)
    offsets = [(i * step, j * step) for i in range(-reach, reach + 1) for j in range(-reach, reach + 1)
               if math.hypot(i * step, j * step) <= radius]
    return [Vec3(x=stop.x + dx, y=stop.y + dy, z=stop.z) for dx, dy in sorted(offsets, key=lambda o: math.hypot(*o))]


def _turning_space_near(ctx: CheckContext, rule: RuleSpec, stop: Vec3, setback: Vec3) -> Settled:
    """The fixed setback spot if a circle fits there, else the nearest spot to the stop where one fits.

    With no fit anywhere, the setback spot is reported, so the finding keeps pointing where a customer
    arriving head-on would turn.
    """
    radius = to_meters(rule.parameter("circle_diameter_inches")) / 2
    return first_fit(
        [setback, *_centres_near(stop, radius)],
        lambda at: ctx.measure.turning_space(ctx.graph, at),
        turning_counted(ctx),
        lambda space: fits_turning_circle(space, rule),
    )


def _pointed_at(ctx: CheckContext, rule: RuleSpec, settled: Settled, satisfied: bool) -> list[UUID]:
    """What the finding shows: the pieces it counted the space under, or what stands in the circle."""
    if satisfied or settled.look_under:
        return list(settled.pieces)
    diameter = to_meters(rule.parameter("circle_diameter_inches"))
    return intruders(ctx.graph, rectangle(settled.at, diameter, diameter))


def _at_stop(ctx: CheckContext, rule: RuleSpec, stop_index: int) -> Observation:
    stops = ctx.scenario.stops
    setback = setback_point(stops, stop_index, to_meters(APPROACH_SETBACK_INCHES))
    settled = _turning_space_near(ctx, rule, stops[stop_index].position, setback)
    satisfied = fits_turning_circle(settled.space, rule)
    return Observation(
        rule_id=RULE_ID,
        satisfied=satisfied,
        measured_inches=square_side(settled.space),
        required_inches=rule.parameter("circle_diameter_inches"),
        relied_on=settled.pieces,
        locus=region_locus(settled.space, _pointed_at(ctx, rule, settled, satisfied), circle=True),
        facts={"stop": stops[stop_index].name, **settled.facts(ctx)},
        dedupe_key=(RULE_ID, stops[stop_index].name),
        reason=_reason(settled, satisfied),
        asks_for=settled.asks_for,
    )


def _reason(settled: Settled, satisfied: bool) -> str:
    if settled.look_under:
        return "unseen_floor"
    return "measured" if satisfied else "too_tight"
