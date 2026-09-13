"""ADA 2010 904.4.1, and the clear floor space 305.3 it refers to.

Two separate numbers, so two separate checks: how high the counter is, and
whether there is room to pull up alongside it. A counter can fail one and pass
the other, and the fix for each is a different sentence.
"""

from __future__ import annotations

from standardphysics_pipeline import region_locus

from ..rules import RuleSpec
from ..tracing import traced
from . import roles
from .clear_floor import fits_rectangle
from .context import CheckContext
from .observation import Observation
from .vertical import height_locus

HEIGHT_RULE = "service_counter_height"
APPROACH_RULE = "service_counter_approach"


@traced("checks.service_counter_height")
def service_counter_height(ctx: CheckContext) -> list[Observation]:
    rule = ctx.rule(HEIGHT_RULE)
    observations = []
    for counter in roles.service_counters(ctx.graph):
        result = ctx.measure.counter_height(ctx.graph, counter.id)
        observations.append(
            Observation(
                rule_id=HEIGHT_RULE,
                satisfied=rule.satisfied_by(result.inches),
                measured_inches=result.inches,
                required_inches=rule.threshold,
                relied_on=(counter.id,),
                locus=height_locus(counter, result),
                facts={
                    "counter": counter.label,
                    "accessible_length_inches": rule.parameter(
                        "accessible_length_min_inches"
                    ),
                },
                dedupe_key=(HEIGHT_RULE, str(counter.id)),
                reason="measured",
            )
        )
    return observations


@traced("checks.service_counter_approach")
def service_counter_approach(ctx: CheckContext) -> list[Observation]:
    rule = ctx.rule(APPROACH_RULE)
    observations = []
    for counter in roles.service_counters(ctx.graph):
        result = ctx.measure.counter_approach(ctx.graph, counter.id)
        observations.append(_approach(ctx, rule, counter, result))
    return observations


def _approach(ctx: CheckContext, rule: RuleSpec, counter, result) -> Observation:
    required_wide = rule.parameter("clear_width_min_inches")
    required_deep = rule.parameter("clear_depth_min_inches")
    satisfied = fits_rectangle(result, required_wide, required_deep)
    return Observation(
        rule_id=APPROACH_RULE,
        satisfied=satisfied,
        measured_inches=min(result.inches_wide, result.inches_deep),
        required_inches=rule.threshold,
        relied_on=(counter.id,),
        locus=region_locus(result, [counter.id]),
        facts={
            "counter": counter.label,
            "measured_wide": result.inches_wide,
            "measured_deep": result.inches_deep,
            "required_wide": required_wide,
            "required_deep": required_deep,
        },
        dedupe_key=(APPROACH_RULE, str(counter.id)),
        reason="measured" if satisfied else "too_small",
    )
