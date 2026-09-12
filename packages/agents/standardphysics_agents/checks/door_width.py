"""ADA 2010 404.2.3. Whether a wheelchair fits through the doorway.

The section measures between the face of the door and the stop with the door
open 90 degrees. A scan sees the doorway, not the swing, so a provider that
knows it is reporting the opening rather than the clear width says so with
`needs_measurement`, and the finding becomes a request for that one number.
"""

from __future__ import annotations

from standardphysics_contracts import WidthResult
from standardphysics_pipeline import width_locus

from ..tracing import traced
from . import roles
from .context import CheckContext
from .observation import Observation

RULE_ID = "door_clear_width"


def needs_measurement(result: WidthResult) -> bool:
    """Read off the result, so this starts working the day Lane D adds it."""
    return bool(getattr(result, "needs_measurement", False))


@traced("check.door_clear_width")
def door_clear_width(ctx: CheckContext) -> list[Observation]:
    rule = ctx.rule(RULE_ID)
    observations = []
    for door in roles.doors(ctx.graph):
        result = ctx.measure.door_clear_width(ctx.graph, door.id)
        asking = needs_measurement(result)
        observations.append(
            Observation(
                rule_id=RULE_ID,
                satisfied=rule.satisfied_by(result.inches),
                measured_inches=None if asking else result.inches,
                required_inches=rule.threshold,
                relied_on=(door.id,),
                locus=width_locus(ctx.graph, result),
                facts={"door": door.label, "opening_inches": result.inches},
                dedupe_key=(RULE_ID, str(door.id)),
                reason="needs_tape_measure" if asking else "measured",
                asks_for="measurement" if asking else None,
            )
        )
    return observations
