"""Every tier 1 check, and the one call that runs them.

A check runs only when a person has verified its rule, so the registry pairs
each function with the rules it answers rather than calling everything and
filtering afterwards.
"""

from __future__ import annotations

from typing import Callable, Iterable

from standardphysics_contracts.rules import Tier

from ..tracing import traced
from .context import CheckContext
from .dedupe import dedupe
from .door_width import door_clear_width
from .exit_path import exit_path
from .observation import Observation, Unevaluated
from .passing_space import passing_space
from .questions import RULE_IDS as QUESTION_RULE_IDS
from .questions import scan_cannot_see
from .result import CheckResult, as_result
from .route_width import route_clear_width, route_width_verdict
from .service_counter import service_counter_approach, service_counter_height
from .turn_width import turn_clear_width, turn_verdict
from .turning_space import turning_space

CheckFn = Callable[[CheckContext], CheckResult | Iterable[Observation]]

REGISTRY: tuple[tuple[frozenset[str], CheckFn], ...] = (
    (frozenset({"route_clear_width"}), route_clear_width),
    (frozenset({"turn_clear_width"}), turn_clear_width),
    (frozenset({"passing_space"}), passing_space),
    (frozenset({"turning_space"}), turning_space),
    (frozenset({"door_clear_width"}), door_clear_width),
    (frozenset({"service_counter_height"}), service_counter_height),
    (frozenset({"service_counter_approach"}), service_counter_approach),
    (frozenset({"exit_path"}), exit_path),
    (QUESTION_RULE_IDS, scan_cannot_see),
)


def _waiting_on_a_reader(ctx: CheckContext, max_tier: Tier) -> list[Unevaluated]:
    """Rules we hold that nobody has read yet.

    An empty report and a clean shop look identical from the outside, so a rule
    that is switched off for want of a reader says so here. This is how the API
    and the team find out, and it never reaches the owner.
    """
    enabled = {rule.id for rule in ctx.rules.enabled(ctx.ledger, max_tier)}
    return [
        Unevaluated(
            rule.id,
            f"a person to read {rule.citation.authority} {rule.citation.section} "
            f"and confirm {rule.threshold:g} {rule.unit}: "
            f"cli rules verify {rule.id} --by \"<name>\"",
        )
        for rule in ctx.rules.within_tier(max_tier)
        if rule.id not in enabled
    ]


@traced("checks.run")
def run_checks(ctx: CheckContext, max_tier: Tier = 1) -> CheckResult:
    enabled = {rule.id for rule in ctx.rules.enabled(ctx.ledger, max_tier)}
    observations: list[Observation] = []
    unevaluated: list[Unevaluated] = _waiting_on_a_reader(ctx, max_tier)

    for rule_ids, check in REGISTRY:
        if not rule_ids & enabled:
            continue
        result = as_result(check(ctx))
        observations.extend(o for o in result.observations if o.rule_id in enabled)
        unevaluated.extend(result.unevaluated)

    return CheckResult(dedupe(observations, ctx.rules), unevaluated)


__all__ = [
    "CheckContext", "CheckResult", "Observation", "REGISTRY", "Unevaluated",
    "dedupe", "door_clear_width", "exit_path", "passing_space", "route_clear_width",
    "route_width_verdict", "run_checks", "scan_cannot_see",
    "service_counter_approach", "service_counter_height", "turn_clear_width",
    "turn_verdict", "turning_space",
]
