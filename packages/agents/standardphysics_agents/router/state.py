"""What the router is allowed to see when it picks the next action.

Findings, how many passes have run, how many fixes have been tried, and which
findings furniture can actually resolve. No geometry, no keys, and no way to
change a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from standardphysics_contracts import Finding, SceneGraph
from standardphysics_contracts.loop import RouterAction

from ..rules import AgentRulePack

MAX_FIX_ATTEMPTS = 3
"""After three failed proposals the loop stops proposing. Plan section 10."""


@dataclass(frozen=True)
class RouterState:
    findings: list[Finding]
    pass_number: int
    fix_attempts: int = 0
    fixable_finding_ids: tuple[UUID, ...] = ()
    """Problems with at least one movable thing causing them."""

    rescan_finding_ids: tuple[UUID, ...] = ()
    """Answers resting on geometry we want another look at."""

    unevaluated: tuple[str, ...] = ()
    actions_taken: tuple[RouterAction, ...] = ()
    """What this loop has already done, so it does not do it twice.

    Asking the owner the same question on every pass is not a loop, it is a
    stutter.
    """

    @property
    def last_action(self) -> RouterAction | None:
        return self.actions_taken[-1] if self.actions_taken else None

    @property
    def problems(self) -> list[Finding]:
        return [f for f in self.findings if f.outcome == "problem"]

    @property
    def questions(self) -> list[Finding]:
        return [f for f in self.findings if f.outcome == "question"]

    @property
    def fix_budget_left(self) -> int:
        return max(MAX_FIX_ATTEMPTS - self.fix_attempts, 0)

    def summary(self) -> dict:
        """The shape that goes over the wire."""
        return {
            "pass_number": self.pass_number,
            "fix_attempts": self.fix_attempts,
            "fix_attempts_remaining": self.fix_budget_left,
            "last_action": self.last_action,
            "actions_taken": list(self.actions_taken),
            "unevaluated_rules": list(self.unevaluated),
            "findings": [self._finding_summary(f) for f in self.findings],
        }

    def _finding_summary(self, finding: Finding) -> dict:
        return {
            "id": str(finding.id),
            "check_id": finding.check_id,
            "outcome": finding.outcome,
            "title": finding.title,
            "measured_inches": finding.measured_inches,
            "required_inches": finding.required_inches,
            "citation": finding.citation.display(),
            "furniture_can_fix": finding.id in self.fixable_finding_ids,
            "wants_another_look": finding.id in self.rescan_finding_ids,
        }


def _movable_cause(finding: Finding, graph: SceneGraph) -> bool:
    if finding.locus is None:
        return False
    for node_id in finding.locus.node_ids:
        try:
            if graph.by_id(node_id).movable:
                return True
        except KeyError:
            continue
    return False


def _wants_another_look(finding: Finding, rules: AgentRulePack) -> bool:
    """A question about something we did measure is a question about coverage."""
    if finding.outcome != "question":
        return False
    try:
        return rules.by_id(finding.check_id).measurable
    except KeyError:
        return False


def state_for(
    findings: list[Finding],
    graph: SceneGraph,
    rules: AgentRulePack,
    *,
    pass_number: int = 1,
    fix_attempts: int = 0,
    unevaluated: tuple[str, ...] = (),
    actions_taken: tuple[RouterAction, ...] = (),
) -> RouterState:
    return RouterState(
        findings=findings,
        pass_number=pass_number,
        fix_attempts=fix_attempts,
        fixable_finding_ids=tuple(
            f.id
            for f in findings
            if f.outcome == "problem" and _movable_cause(f, graph)
        ),
        rescan_finding_ids=tuple(
            f.id for f in findings if _wants_another_look(f, rules)
        ),
        unevaluated=unevaluated,
        actions_taken=actions_taken,
    )
