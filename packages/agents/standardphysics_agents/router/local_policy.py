"""A local policy, labelled as one.

If the router is not available, the loop still has to decide something, and the
worst way to handle that would be to quietly make the same choices under the
router's name. This carries `provider="local_policy"` on every decision it
makes, so a trace, a report and a demo all say which one answered.

The order of the rules is the argument. Coverage before measurement, because
measuring geometry nobody is sure of produces confident nonsense. Furniture
before people, because a rearrangement costs the owner nothing to look at and a
question costs them a trip across the shop. A professional last, because
escalating something a table could have solved wastes somebody's afternoon.
"""

from __future__ import annotations

from typing import Callable

from standardphysics_contracts import Decision

from ..tracing import traced
from .decision import Rejected, parse_decision
from .state import RouterState

PROVIDER = "local_policy"

Rule = Callable[[RouterState], dict | None]


def _rescan_thin_coverage(state: RouterState) -> dict | None:
    if "RESCAN_AREA" in state.actions_taken or not state.rescan_finding_ids:
        return None
    return {
        "action": "RESCAN_AREA",
        "target_finding_ids": [str(i) for i in state.rescan_finding_ids],
        "rationale": "Some of this rests on geometry worth a second look.",
    }


def _fix_what_furniture_can(state: RouterState) -> dict | None:
    if not state.fix_budget_left:
        return None
    targets = [f.id for f in state.problems if f.id in state.fixable_finding_ids]
    if not targets:
        return None
    return {
        "action": "FIX",
        "target_finding_ids": [str(i) for i in targets],
        "rationale": "Moving furniture can clear these.",
    }


def _ask_the_owner(state: RouterState) -> dict | None:
    if "ASK_OWNER" in state.actions_taken or not state.questions:
        return None
    return {
        "action": "ASK_OWNER",
        "target_finding_ids": [str(state.questions[0].id)],
        "question": state.questions[0].title,
        "rationale": "This one needs something only the owner can send.",
    }


def _escalate_the_rest(state: RouterState) -> dict | None:
    if "ESCALATE" in state.actions_taken:
        return None
    stuck = [f.id for f in state.problems if f.id not in state.fixable_finding_ids]
    if not stuck:
        return None
    return {
        "action": "ESCALATE",
        "target_finding_ids": [str(i) for i in stuck],
        "rationale": "Furniture cannot clear these.",
    }


def _finish(state: RouterState) -> dict:
    return {"action": "DONE", "rationale": "Everything measurable is answered."}


POLICY: tuple[Rule, ...] = (
    _rescan_thin_coverage,
    _fix_what_furniture_can,
    _ask_the_owner,
    _escalate_the_rest,
)


class LocalPolicyRouter:
    """The fallback the plan allows, with the claim dropped rather than hidden."""

    provider = PROVIDER

    @traced("router.local_policy")
    def decide(self, state: RouterState) -> Decision | Rejected:
        for rule in POLICY:
            payload = rule(state)
            if payload is not None:
                return parse_decision(
                    payload,
                    state.findings,
                    PROVIDER,
                    fixable_finding_ids=state.fixable_finding_ids,
                    rescan_finding_ids=state.rescan_finding_ids,
                )
        return parse_decision(
            _finish(state),
            state.findings,
            PROVIDER,
            fixable_finding_ids=state.fixable_finding_ids,
            rescan_finding_ids=state.rescan_finding_ids,
        )
