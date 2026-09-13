"""What comes back from a question, and what an executor is given to answer it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from standardphysics_contracts import (
    Finding,
    Locus,
    MeasurementProvider,
    Proposal,
    Scenario,
    SceneGraph,
)
from standardphysics_contracts.rules import Tier

from ..assess import Pass, assess
from ..rules import AgentRulePack, VerificationLedger
from .query import Query, QueryKind


@dataclass(frozen=True)
class Answer:
    text: str
    """The sentence the owner reads."""

    kind: QueryKind | None = None
    query: Query | None = None
    subjects: tuple[UUID, ...] = ()
    locus: Locus | None = None
    """Where to look, so the viewer flies to whatever was asked about."""

    data: dict[str, Any] = field(default_factory=dict)
    """The numbers behind the sentence, for a table or a label."""

    rejected: str | None = None
    proposal: Proposal | None = None
    graph: SceneGraph | None = None
    """A layout to show as a before and after, when the answer moved something."""

    findings: tuple[Finding, ...] = ()

    @property
    def understood(self) -> bool:
        return self.kind is not None


@dataclass(frozen=True)
class AskContext:
    """Everything an executor may look at.

    It can measure and it can read the model of the room. It has no way to
    write a dimension, and neither does anything it calls.
    """

    graph: SceneGraph
    scenario: Scenario
    measure: MeasurementProvider
    rules: AgentRulePack
    ledger: VerificationLedger
    max_tier: Tier = 1
    _baseline: list[Pass] = field(default_factory=list, repr=False)

    def baseline(self) -> Pass:
        """The current assessment, measured once however often it is asked for."""
        if not self._baseline:
            self._baseline.append(
                assess(
                    self.graph,
                    self.scenario,
                    self.measure,
                    rules=self.rules,
                    ledger=self.ledger,
                    max_tier=self.max_tier,
                )
            )
        return self._baseline[0]
