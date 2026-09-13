"""ADA 2010 902.3 and 226.1. Somewhere to sit and put a drink down.

Two requirements, and the pack keeps them apart because they fail differently.
902.3 is a height: a dining surface belongs between 28 and 34 inches. 226.1 is
a share: at least five percent of the seating has to be at one that complies.
A shop can have every table the wrong height, or the right height on one table
out of forty, and those are different conversations with the owner.
"""

from __future__ import annotations

import math

from standardphysics_contracts import SceneNode, to_inches

from ..rules import RuleSpec
from ..tracing import traced
from . import roles
from .context import CheckContext
from .observation import Observation
from .vertical import mounted_locus

RULE_ID = "dining_surface_height"


def surface_height_inches(node: SceneNode) -> float:
    """The top of the table, above the floor."""
    return to_inches(node.transform.position.z + node.dimensions.z / 2)


def within_range(height: float, rule: RuleSpec) -> bool:
    return (
        rule.parameter("surface_min_inches")
        <= height
        <= rule.parameter("surface_max_inches")
    )


def required_count(total: int, rule: RuleSpec) -> int:
    """Five percent, and never fewer than one where there is any seating."""
    if total == 0:
        return 0
    return max(1, math.ceil(total * rule.parameter("accessible_share")))


@traced("check.dining_surface_height")
def dining_surface_height(ctx: CheckContext) -> list[Observation]:
    rule = ctx.rule(RULE_ID)
    surfaces = roles.dining_surfaces(ctx.graph)
    if not surfaces:
        return []

    heights = {node.id: surface_height_inches(node) for node in surfaces}
    complying = [node for node in surfaces if within_range(heights[node.id], rule)]
    needed = required_count(len(surfaces), rule)
    return [
        Observation(
            rule_id=RULE_ID,
            satisfied=len(complying) >= needed,
            measured_inches=min(heights.values()),
            required_inches=rule.threshold,
            relied_on=tuple(node.id for node in surfaces),
            locus=mounted_locus(surfaces[0]),
            facts={
                "surfaces": len(surfaces),
                "complying": len(complying),
                "needed": needed,
                "lowest": min(heights.values()),
                "highest": max(heights.values()),
                "range_low": rule.parameter("surface_min_inches"),
                "range_high": rule.parameter("surface_max_inches"),
            },
            dedupe_key=(RULE_ID,),
            reason="measured" if len(complying) >= needed else "too_few_at_height",
        )
    ]
