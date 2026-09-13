"""One configuration of the review, and running a case under it.

A configuration is the set of knobs that change what the system does without
changing what a correct answer is: which measurement pipeline answers, which
router decides, whether the fix agent runs, how deep its ladder goes, and
whether the rule pack is treated as verified. The cases carry their own tier,
so tier is not one.

Two things publish these runs. `weave_eval.py` scores them as a Weave
Evaluation, where the Evals tab draws a mean per scorer and a side by side.
`experiments.py` logs them as W&B runs, where each knob is a hyperparameter and
ARIA can read the grid. Both describe the same configuration, so it is defined
here once and imported.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, replace
from typing import Any, Callable

from ..rules import VerificationLedger, load_ledger, load_pack
from .dataset import Case, dataset
from .runner import FIX_CANDIDATE_LIMIT, action_name, run_case
from .scorers import SCORERS, CaseOutcome

PREVIEW_REVIEWER = "unverified preview (development only)"
"""Mirrors the server's SP_PREVIEW_UNVERIFIED_RULES: a way to see the numbers
before the rule pack has been read by a person. A run made this way is not
evidence about a shop, and the run records the flag that produced it."""


@dataclass(frozen=True)
class Setup:
    label: str
    measurements: str = "pipeline"
    router: str = "local"
    run_fixes: bool = True
    fix_candidates: int = FIX_CANDIDATE_LIMIT
    preview_unverified: bool = False

    def fields(self) -> dict[str, Any]:
        return {
            "measurements": self.measurements,
            "router": self.router,
            "run_fixes": self.run_fixes,
            "fix_candidates": self.fix_candidates,
            "preview_unverified": self.preview_unverified,
        }


DEFAULT_SETUPS = (
    Setup("pipeline measurements, fixes on"),
    Setup("stub measurements, fixes on", measurements="stub"),
    Setup("pipeline measurements, fixes off", run_fixes=False),
)
"""The shipped path, then one part of it replaced at a time.

The stub run is a control, not a rival: `FixtureMeasurements` merges
axis-aligned boxes along a straight leg, which is right for the shipped shop
and wrong for cases that move the geometry. Reading it against the pipeline
says how much of the score is the measurement rather than the rule. Holding
the fix agent back says what the fixes cost the other scorers."""


LABELS: dict[str, Callable[[Any], str | None]] = {
    "measurements": lambda value: f"{value} measurements",
    "router": lambda value: f"{value} router",
    "run_fixes": lambda value: None if value else "fixes off",
    "fix_candidates": lambda value: f"{value} candidates",
    "preview_unverified": lambda value: "unverified preview" if value else None,
}
"""How each knob reads in a run name. `None` leaves the knob out, because a
name should say what is unusual about a configuration rather than restate every
default."""


def label_for(fields: dict[str, Any]) -> str:
    parts = [LABELS[name](value) for name, value in fields.items() if name in LABELS]
    return ", ".join(part for part in parts if part) or "defaults"


def setup(**fields: Any) -> Setup:
    """A configuration named after the knobs it sets."""
    return Setup(label=label_for(fields), **fields)


def previewing(setups: tuple[Setup, ...] | list[Setup]) -> list[Setup]:
    """The same configurations, scored as if a person had verified every rule."""
    return [replace(each, preview_unverified=True) for each in setups]


def summary(outcome: CaseOutcome) -> dict[str, Any]:
    """What the system said about one case, and what every scorer made of it."""
    return {
        "problems": sorted(outcome.reported_problems),
        "questions": sorted(outcome.reported_questions),
        "action": action_name(outcome),
        "unevaluated": [gap.rule_id for gap in outcome.result.unevaluated],
        "fix_found": outcome.fix.found if outcome.fix else None,
        "gate_accepted": outcome.gate.accepted if outcome.gate else None,
        "error": outcome.error,
        "scores": {name: score(outcome) for name, score in SCORERS.items()},
    }


def review(configuration: Any, case_id: str) -> dict[str, Any]:
    """Run one case through one configuration.

    `configuration` is anything carrying the knobs: a `Setup`, or the Weave
    model built from one, so the configuration is named in a single place.
    """
    outcome = run_case(
        case(case_id),
        measurements(configuration.measurements),
        load_pack(),
        ledger(configuration.preview_unverified),
        router(configuration.router),
        configuration.run_fixes,
        fix_candidates=getattr(
            configuration, "fix_candidates", FIX_CANDIDATE_LIMIT
        ),
    )
    return summary(outcome)


@functools.lru_cache(maxsize=1)
def _cases_by_id() -> dict[str, Case]:
    return {each.id: each for each in dataset()}


def case(case_id: str) -> Case:
    found = _cases_by_id().get(case_id)
    if found is None:
        raise KeyError(f"no case named {case_id}")
    return found


@functools.lru_cache(maxsize=2)
def measurements(name: str):
    if name == "stub":
        from standardphysics_fixtures import FixtureMeasurements

        return FixtureMeasurements()
    from standardphysics_pipeline import PipelineMeasurements

    return PipelineMeasurements()


@functools.lru_cache(maxsize=2)
def router(name: str):
    from ..router import LocalPolicyRouter, TypeSafeRouter

    return TypeSafeRouter() if name == "typesafe" else LocalPolicyRouter()


@functools.lru_cache(maxsize=2)
def ledger(preview_unverified: bool) -> VerificationLedger:
    if not preview_unverified:
        return load_ledger()
    verified = VerificationLedger()
    for rule in load_pack().rules:
        verified = verified.record(rule, verified_by=PREVIEW_REVIEWER)
    return verified


__all__ = [
    "DEFAULT_SETUPS", "LABELS", "PREVIEW_REVIEWER", "Setup", "case",
    "label_for", "ledger", "measurements", "previewing", "review", "router",
    "setup", "summary",
]
