"""The same cases and the same scorers, run as a Weave Evaluation.

`evaluate()` in runner.py scores one run and writes the rows to disk. This
module puts the same work in Weave's Evals tab, which draws a mean per scorer,
the per-case table behind each mean, and a side by side when the same cases are
scored against more than one configuration of the system. Comparing
configurations is the point: each one changes a single part and the columns say
what that part is worth. Swapping Lane B's measurement pipeline for the
fixtures' simplified stand-in is how you find out how much of the score rests
on measuring the room rather than on the rules.

Scoring stays in scorers.py. A scorer there reads a whole `CaseOutcome` — the
assessment before a fix, the one after, the node ids each label resolved to,
the inches measured per check — which is more than a dataset row can hold, so
each scorer here reports the number that module already computed instead of
recomputing it from the row. A threshold and a score each keep one definition.

Weave is optional everywhere else in this lane and stays optional here: import
this module without it installed and nothing happens until you call something,
which then says what to install.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from dataclasses import dataclass, replace
from typing import Any

from ..rules import VerificationLedger, load_ledger, load_pack
from .dataset import Case, dataset
from .runner import action_name, run_case
from .scorers import LOWER_IS_BETTER, SCORERS, CaseOutcome

DEFAULT_NAME = "shop-review"

PREVIEW_REVIEWER = "unverified preview (development only)"
"""Mirrors the server's SP_PREVIEW_UNVERIFIED_RULES: a way to see the numbers
before the rule pack has been read by a person. A run made this way is not
evidence about a shop, and the Evals tab shows the flag that produced it."""


@dataclass(frozen=True)
class Setup:
    """One configuration of the review, scored against every case.

    These are the knobs that change what the system does without changing what
    a correct answer is. The cases carry their own tier, so tier is not one.
    """

    label: str
    measurements: str = "pipeline"
    router: str = "local"
    run_fixes: bool = True
    preview_unverified: bool = False

    def fields(self) -> dict[str, Any]:
        return {
            "measurements": self.measurements,
            "router": self.router,
            "run_fixes": self.run_fixes,
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


def rows(cases: list[Case] | None = None) -> list[dict[str, Any]]:
    """One row per case, holding what a correct answer looks like.

    The scene graph stays out. A row is what someone reads in the Evals table
    to see what the case asked for, and `predict` looks the geometry up by id.
    """
    return [
        {
            "case": case.id,
            "description": case.description,
            "expected_problems": sorted(case.expected_problems),
            "forbidden_problems": sorted(case.forbidden_problems),
            "expected_questions": sorted(case.expected_questions),
            "expected_action": case.expected_action,
            "expects_a_fix": case.fix_should_resolve,
            "tier": case.max_tier,
        }
        for case in (cases if cases is not None else dataset())
    ]


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


def review(setup: Any, case_id: str) -> dict[str, Any]:
    """Run one case through one configuration.

    `setup` is anything carrying the four fields: a `Setup`, or the Weave model
    built from one, so the configuration is named in a single place.
    """
    outcome = run_case(
        _case(case_id),
        _measurements(setup.measurements),
        load_pack(),
        _ledger(setup.preview_unverified),
        _router(setup.router),
        setup.run_fixes,
    )
    return summary(outcome)


def scorer(module: Any, name: str):
    """A Weave scorer reporting one number scorers.py already computed."""
    direction = " Lower is better." if name in LOWER_IS_BETTER else ""

    def score(output: dict[str, Any] | None) -> float | None:
        return (output or {}).get("scores", {}).get(name)

    score.__name__ = name
    score.__doc__ = f"{name}, from the evaluation's own scorers.{direction}"
    return module.op(score)


def evaluate_in_weave(
    setups: list[Setup] | tuple[Setup, ...] | None = None,
    *,
    cases: list[Case] | None = None,
    name: str = DEFAULT_NAME,
) -> dict[str, dict[str, Any]]:
    """Score every configuration against every case, in Weave.

    Returns Weave's own summary per configuration. `weave.init()` has to have
    run first, which `init_tracing()` does.
    """
    module = _weave()
    picked = list(cases if cases is not None else dataset())
    evaluation = _evaluation(module, picked, name)
    model_class = _model_class(module)
    scored: dict[str, dict[str, Any]] = {}
    for setup in setups if setups is not None else DEFAULT_SETUPS:
        scored[setup.label] = _scored(evaluation, model_class(**setup.fields()))
        _flush(module)
    return scored


def _scored(evaluation: Any, model: Any) -> dict[str, Any]:
    """`Evaluation.evaluate` is a coroutine in current Weave, and was a plain
    call in earlier ones. A scorer may not care which."""
    result = evaluation.evaluate(model)
    if inspect.isawaitable(result):
        return asyncio.run(_awaited(result))
    return result


async def _awaited(awaitable: Any) -> dict[str, Any]:
    return await awaitable


def _flush(module: Any) -> None:
    """Calls upload in the background and a command exits as soon as it prints.

    Pushing each configuration out before the next one starts means a dropped
    connection costs that run rather than every run behind it.
    """
    client = getattr(module, "get_client", lambda: None)()
    flush = getattr(client, "flush", None)
    if flush is not None:
        flush()


def _evaluation(module: Any, cases: list[Case], name: str):
    return module.Evaluation(
        name=name,
        description=(
            f"{len(cases)} labelled cases from the rule pack, scored by "
            f"{', '.join(sorted(SCORERS))}."
        ),
        dataset=module.Dataset(name=f"{name}-cases", rows=rows(cases)),
        scorers=[scorer(module, metric) for metric in SCORERS],
    )


@functools.lru_cache(maxsize=1)
def _model_class(module: Any):
    """Built on first use, because the base class comes from Weave.

    The fields are the configuration, so the Evals tab names what produced each
    column of numbers rather than leaving it to whoever reads them.
    """

    class ShopReview(module.Model):
        measurements: str = "pipeline"
        router: str = "local"
        run_fixes: bool = True
        preview_unverified: bool = False

        @module.op
        def predict(self, case: str) -> dict[str, Any]:
            return review(self, case)

    return ShopReview


def _weave() -> Any:
    try:
        import weave
    except ImportError as error:
        raise RuntimeError(
            "Weave evaluations need: "
            "python -m pip install -e 'packages/agents[observability]'"
        ) from error
    return weave


@functools.lru_cache(maxsize=1)
def _cases_by_id() -> dict[str, Case]:
    return {case.id: case for case in dataset()}


def _case(case_id: str) -> Case:
    case = _cases_by_id().get(case_id)
    if case is None:
        raise KeyError(f"no case named {case_id}")
    return case


@functools.lru_cache(maxsize=2)
def _measurements(name: str):
    if name == "stub":
        from standardphysics_fixtures import FixtureMeasurements

        return FixtureMeasurements()
    from standardphysics_pipeline import PipelineMeasurements

    return PipelineMeasurements()


@functools.lru_cache(maxsize=2)
def _router(name: str):
    from ..router import LocalPolicyRouter, TypeSafeRouter

    return TypeSafeRouter() if name == "typesafe" else LocalPolicyRouter()


@functools.lru_cache(maxsize=2)
def _ledger(preview_unverified: bool) -> VerificationLedger:
    if not preview_unverified:
        return load_ledger()
    ledger = VerificationLedger()
    for rule in load_pack().rules:
        ledger = ledger.record(rule, verified_by=PREVIEW_REVIEWER)
    return ledger


def previewing(setups: tuple[Setup, ...] | list[Setup]) -> list[Setup]:
    """The same configurations, scored as if a person had verified every rule."""
    return [replace(setup, preview_unverified=True) for setup in setups]


__all__ = [
    "DEFAULT_NAME", "DEFAULT_SETUPS", "PREVIEW_REVIEWER", "Setup",
    "evaluate_in_weave", "previewing", "review", "rows", "scorer", "summary",
]
