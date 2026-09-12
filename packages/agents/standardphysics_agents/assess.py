"""One pass over a shop: measure everything, then say what it means.

The result is an `Assessment`, which is what Lane D renders and what the gate
compares between passes. `unevaluated` rides alongside it rather than inside
it, because a rule we could not answer is news for the team and not a card for
the owner.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from standardphysics_contracts import (
    Assessment,
    Decision,
    Finding,
    MeasurementProvider,
    Scenario,
    SceneGraph,
)
from standardphysics_contracts.rules import Tier

from .checks import CheckContext, Unevaluated, run_checks
from .findings import to_findings
from .hashing import graph_hash
from .rules import AgentRulePack, VerificationLedger, load_ledger, load_pack
from .tracing import project_url, traced

ASSESSMENT_NAMESPACE = uuid.UUID("7b3c1f04-5e2a-4c6b-9d18-000000000003")


@dataclass(frozen=True)
class Pass:
    """What one trip round the loop produced."""

    assessment: Assessment
    unevaluated: list[Unevaluated] = field(default_factory=list)

    @property
    def findings(self) -> list[Finding]:
        return self.assessment.findings

    @property
    def problems(self) -> list[Finding]:
        return self.assessment.problems

    @property
    def questions(self) -> list[Finding]:
        return self.assessment.questions


def _assessment_id(graph_fingerprint: str, version: str, pass_number: int) -> uuid.UUID:
    return uuid.uuid5(
        ASSESSMENT_NAMESPACE, f"{graph_fingerprint}|{version}|{pass_number}"
    )


@traced("assess")
def assess(
    graph: SceneGraph,
    scenario: Scenario,
    measure: MeasurementProvider,
    *,
    rules: AgentRulePack | None = None,
    ledger: VerificationLedger | None = None,
    pass_number: int = 1,
    max_tier: Tier = 1,
    decision: Decision | None = None,
) -> Pass:
    pack = rules or load_pack()
    verified = ledger if ledger is not None else load_ledger()
    context = CheckContext(
        graph=graph, scenario=scenario, measure=measure, rules=pack, ledger=verified
    )
    result = run_checks(context, max_tier)
    fingerprint = graph_hash(graph)
    assessment = Assessment(
        id=_assessment_id(fingerprint, pack.version, pass_number),
        scan_id=graph.scan_id,
        graph_revision=graph.revision,
        graph_hash=fingerprint,
        rulepack_version=pack.version,
        pass_number=pass_number,
        created_at=datetime.now(timezone.utc),
        findings=to_findings(result.observations, pack, graph, graph.scan_id),
        decision=decision,
        weave_run_url=project_url(),
    )
    return Pass(assessment=assessment, unevaluated=list(result.unevaluated))
