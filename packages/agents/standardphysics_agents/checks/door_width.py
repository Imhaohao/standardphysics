"""ADA 2010 404.2.3. Whether a wheelchair fits through the doorway."""

from __future__ import annotations

from standardphysics_pipeline import width_locus

from ..tracing import traced
from . import roles
from .context import CheckContext
from .observation import Observation

RULE_ID = "door_clear_width"


@traced("check.door_clear_width")
def door_clear_width(ctx: CheckContext) -> list[Observation]:
    rule = ctx.rule(RULE_ID)
    observations = []
    for door in roles.doors(ctx.graph):
        result = ctx.measure.door_clear_width(ctx.graph, door.id)
        observations.append(
            Observation(
                rule_id=RULE_ID,
                satisfied=rule.satisfied_by(result.inches),
                measured_inches=result.inches,
                required_inches=rule.threshold,
                relied_on=(door.id,),
                locus=width_locus(ctx.graph, result),
                facts={"door": door.label},
                dedupe_key=(RULE_ID, str(door.id)),
                reason="measured",
            )
        )
    return observations
