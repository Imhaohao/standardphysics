"""Whether a piece of clear floor is big enough, asked the same way every time.

`ClearFloorResult` reports the space it tested and whether that space is clear.
Both matter: a provider can hand back a clear 30 inch square when the rule
wants 60, and it can hand back a 60 inch square with a chair standing in it.
The rule owns the number, so the size comparison happens against the rule pack
rather than against the provider's own verdict.
"""

from __future__ import annotations

from standardphysics_contracts import ClearFloorResult

from ..rules import RuleSpec
from ..rules.pack import COMPARISON_EPSILON


def at_least(measured: float, required: float) -> bool:
    return measured >= required - COMPARISON_EPSILON


def at_most(measured: float, required: float) -> bool:
    return measured <= required + COMPARISON_EPSILON


def square_side(space: ClearFloorResult) -> float:
    return min(space.inches_wide, space.inches_deep)


def fits_square(space: ClearFloorResult, side_inches: float) -> bool:
    return space.fits and at_least(square_side(space), side_inches)


def fits_rectangle(
    space: ClearFloorResult, width_inches: float, depth_inches: float
) -> bool:
    return (
        space.fits
        and at_least(space.inches_wide, width_inches)
        and at_least(space.inches_deep, depth_inches)
    )


def fits_turning_circle(space: ClearFloorResult, rule: RuleSpec) -> bool:
    return fits_square(space, rule.parameter("circle_diameter_inches"))
