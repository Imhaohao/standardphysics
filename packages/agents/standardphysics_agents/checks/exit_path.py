"""California Building Code Chapter 10. Whether there is a way out at all.

Route width asks whether a journey is comfortable. This asks whether the
journey exists, which is a different question with a different consequence.

Chapter 10 also sets an egress width, and which provision governs a shop this
size depends on occupant load. That part is not settled, so this check answers
only the unobstructed half and reports the width half as still waiting on a
person. Reporting a width here as well would put two cards in front of the
owner for one gap, one of them citing a section nobody has pinned.
"""

from __future__ import annotations

from standardphysics_contracts import WidthResult
from standardphysics_pipeline import path_locus

from ..tracing import traced
from .context import CheckContext
from .observation import Observation, Unevaluated
from .result import CheckResult

RULE_ID = "exit_path"

EXIT_STOP_NAMES = frozenset({"exit", "exit door", "way out"})

WAITING_ON = "the egress width section, pinned by a person: see the rule's review note"


@traced("checks.exit_path")
def exit_path(ctx: CheckContext) -> CheckResult:
    legs = [
        ctx.measure.route_clear_width(ctx.graph, ctx.scenario, index)
        for index in ctx.legs()
    ]
    if not legs:
        return CheckResult()
    exit_index = _exit_stop_index(ctx)
    if exit_index is None:
        return CheckResult()
    return CheckResult(
        observations=[_verdict(ctx, legs, exit_index)],
        unevaluated=[Unevaluated(RULE_ID, WAITING_ON)],
    )


def _exit_stop_index(ctx: CheckContext) -> int | None:
    for index, stop in enumerate(ctx.scenario.stops):
        if stop.name.strip().casefold() in EXIT_STOP_NAMES:
            return index
    return len(ctx.scenario.stops) - 1 if ctx.scenario.stops else None


def _verdict(
    ctx: CheckContext, legs: list[WidthResult], exit_index: int
) -> Observation:
    blocked = [index for index, leg in enumerate(legs) if not leg.reachable]
    final = legs[min(max(exit_index - 1, 0), len(legs) - 1)]
    culprit = legs[blocked[0]] if blocked else final
    return Observation(
        rule_id=RULE_ID,
        satisfied=not blocked,
        measured_inches=None,
        required_inches=None,
        relied_on=tuple(culprit.blocking_node_ids),
        locus=path_locus(culprit, label=ctx.stop_name(exit_index)),
        facts={
            "exit": ctx.stop_name(exit_index),
            "blocked_from": [ctx.stop_name(index) for index in blocked],
            "blockers": [ctx.label(n) for n in culprit.blocking_node_ids],
        },
        dedupe_key=(RULE_ID,),
        reason="unreachable" if blocked else "clear",
    )
