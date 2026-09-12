"""ADA 2010 403.5.2. Getting a wheelchair around a 180 degree turn.

The section needs four numbers: how wide the thing being walked around is, and
the clear width approaching the turn, at it, and leaving it. Lane B's
`turn_detail` finds the turn and measures all four.

It also offers its own `passes` and `in_scope`, and this check does not use
them. Thresholds live in the rule pack and in one place only, so what comes
across the seam is the measurement and the verdict is taken here. Otherwise
48 inches exists twice and a person verifying one copy has verified nothing.

A provider with no `turn_detail` cannot answer 403.5.2 at all. Reporting a
route bottleneck as a turn measurement would cite a section we never evaluated,
so that case reports the gap to the team and stays silent to the owner.

The same goes for a turn detected at the very start or end of a leg, where
there is no run of route either side of it to measure. That comes back as a
zone of zero inches, which is not a measurement of anything: nobody built a
doorway with no width. It is reported as a gap rather than as a finding that
the turn is infinitely tight.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from standardphysics_pipeline import width_locus

from ..rules import RuleSpec
from ..tracing import traced
from .context import CheckContext
from .observation import Observation, Unevaluated
from .result import CheckResult

RULE_ID = "turn_clear_width"

WAITING_ON = "a provider with turn_detail: FixtureMeasurements does not measure turns"

UNMEASURED_ZONE = (
    "a turn with route either side of it to measure: one zone came back at zero"
)


@dataclass(frozen=True)
class TurnVerdict:
    applies: bool
    satisfied: bool
    reason: str


def turn_verdict(
    element_width_inches: float,
    approaching_inches: float | None,
    at_turn_inches: float | None,
    leaving_inches: float | None,
    rule: RuleSpec,
) -> TurnVerdict:
    """403.5.2 with its exception, with no geometry in the way.

    A zone Lane B could not measure is None. A measured zone that is too tight
    still fails the turn, but a missing zone never lets it pass.
    """
    exempt = rule.parameter("exempt_at_turn_width_inches")
    if at_turn_inches is not None and at_turn_inches >= exempt:
        return TurnVerdict(False, True, "exempt_wide_turn")
    if element_width_inches >= rule.parameter("element_width_below_inches"):
        return TurnVerdict(False, True, "element_wide_enough")
    tight = _tight_zone(rule, approaching_inches, at_turn_inches, leaving_inches)
    if tight is not None:
        return TurnVerdict(True, False, tight)
    if None in (approaching_inches, at_turn_inches, leaving_inches):
        return TurnVerdict(False, False, "not_fully_measured")
    return TurnVerdict(True, True, "measured")


def _tight_zone(
    rule: RuleSpec,
    approaching: float | None,
    at_turn: float | None,
    leaving: float | None,
) -> str | None:
    zones = (
        ("at_turn_too_tight", at_turn, "at_turn_min_inches"),
        ("approaching_too_tight", approaching, "approaching_min_inches"),
        ("leaving_too_tight", leaving, "leaving_min_inches"),
    )
    for reason, value, parameter in zones:
        if value is not None and value < rule.parameter(parameter):
            return reason
    return None


def binding_zone(turn, rule: RuleSpec) -> tuple[float, float]:
    """The measured zone with the worst shortfall, as (measured, required)."""
    zones = (
        (turn.at_turn_inches, rule.parameter("at_turn_min_inches")),
        (turn.approach_inches, rule.parameter("approaching_min_inches")),
        (turn.leaving_inches, rule.parameter("leaving_min_inches")),
    )
    measured = [pair for pair in zones if pair[0] is not None]
    return min(measured, key=lambda pair: pair[0] - pair[1])


def zones_measured(turn) -> bool:
    """Whether all three of 403.5.2's zones actually got measured.

    Lane B reports an unmeasurable zone as None. A zero would mean the same
    thing and is still rejected, because the two readings have swapped once
    already and a check citing a section is not the place to be relaxed about
    which one arrived.
    """
    zones = (turn.approach_inches, turn.at_turn_inches, turn.leaving_inches)
    return all(zone is not None and zone > 0.0 for zone in zones)


def _pivot_width(turn) -> float:
    """An unidentified element cannot be measured against 48 inches.

    403.5.2 is scoped by the width of the thing walked around, so with no
    element named there is nothing to scope to and the section does not bite.
    """
    return math.inf if turn.pivot_width_inches is None else turn.pivot_width_inches


@traced("check.turn_clear_width")
def turn_clear_width(ctx: CheckContext) -> CheckResult:
    detail = getattr(ctx.measure, "turn_detail", None)
    if detail is None:
        return CheckResult(unevaluated=[Unevaluated(RULE_ID, WAITING_ON)])

    rule = ctx.rule(RULE_ID)
    observations, gaps = [], []
    for index in ctx.legs():
        turn = detail(ctx.graph, ctx.scenario, index)
        if turn is None:
            continue
        if not zones_measured(turn):
            gaps.append(Unevaluated(RULE_ID, UNMEASURED_ZONE))
            continue
        observation = _at_turn(ctx, rule, index, turn)
        if observation is not None:
            observations.append(observation)
    return CheckResult(observations=observations, unevaluated=gaps[:1])


def _at_turn(
    ctx: CheckContext, rule: RuleSpec, leg_index: int, turn
) -> Observation | None:
    verdict = turn_verdict(
        _pivot_width(turn),
        turn.approach_inches,
        turn.at_turn_inches,
        turn.leaving_inches,
        rule,
    )
    if not verdict.applies:
        return None

    measured, required = binding_zone(turn, rule)
    # One element is one turn. An out and back goes round the same shelf on the
    # way in and the way out, and the apex lands a few centimetres apart each
    # time, so keying on where it was would report the same corner twice.
    result = ctx.measure.turn_clear_width(ctx.graph, ctx.scenario, leg_index)
    return Observation(
        rule_id=RULE_ID,
        satisfied=verdict.satisfied,
        measured_inches=measured,
        required_inches=required,
        relied_on=(turn.pivot_id,) if turn.pivot_id else (),
        locus=width_locus(ctx.graph, result),
        facts={
            "destination": ctx.stop_name(leg_index + 1),
            "pivot": ctx.label(turn.pivot_id) if turn.pivot_id else None,
            "approaching": turn.approach_inches,
            "at_turn": turn.at_turn_inches,
            "leaving": turn.leaving_inches,
        },
        dedupe_key=(RULE_ID, str(turn.pivot_id)),
        reason=verdict.reason,
    )
