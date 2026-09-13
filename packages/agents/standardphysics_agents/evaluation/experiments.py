"""The evaluation grid, logged as W&B runs so ARIA can read it.

Weave's Evals tab compares configurations one against another, which is what
you want while you are reading them yourself. ARIA reads runs: a config of flat
hyperparameters, a summary of metrics, and a table behind each run. Given a
grid it will draw the heat map over two axes or the parallel coordinates over
all of them, and say which knob moved which metric. So the same cases and the
same scorers are logged both ways, and neither one re-implements a score.

The grid varies two knobs. `measurements` swaps Lane B's pipeline for the
fixtures' simplified stand-in, which says how much of the score rests on
measuring the room rather than on the rules. `fix_candidates` is how deep the
fix agent's ladder goes before it gives up. Both change what the system does
without changing what a correct answer is.

The question the grid is built to answer: every accuracy scorer sits at 1.000
on this dataset, so the axis with room left in it is what the loop spends to
get there. A configuration that keeps every score and measures fewer candidates
is a faster loop for the same answer.

The local JSON is the authoritative record here, as it is for a single run:
the grid runs and saves with no account, and W&B gets the same numbers when a
key is present.
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..rules import load_pack
from ..tracing import ENTITY_ENV, PROJECT_ENV
from .configuration import Setup, ledger, measurements, router, setup
from .dataset import Case, dataset
from .runner import EvaluationResult, evaluate
from .scorers import LOWER_IS_BETTER, SCORERS

KEY_ENV = "WANDB_API_KEY"

GROUP = "shop-review-grid"

JOB_TYPE = "evaluation"

TAGS = ("shop-review", "evaluation", "aria")

GRID_AXES: dict[str, tuple[Any, ...]] = {
    "measurements": ("pipeline", "stub"),
    "fix_candidates": (4, 8, 16),
}
"""Two axes, so the grid is the shape ARIA draws as a heat map."""

NOTES = (
    "One configuration of the shop review, scored against the labelled cases. "
    "measurements is which pipeline answers a measurement, fix_candidates is "
    "how deep the fix agent searches. "
    f"{', '.join(sorted(LOWER_IS_BETTER))} is an error, so lower is better; "
    "every other score is a share of the cases, so higher is better."
)
"""What each run is, written for whoever or whatever reads it next."""


TABLE_COLUMNS = (
    "case", "description", "problems", "expected_problems", "questions",
    "action", "expected_action", "fix", "gate_accepted", "error",
    *sorted(SCORERS),
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Experiment:
    """One configuration, run, with what it scored and what it spent."""

    setup: Setup
    result: EvaluationResult
    wall_seconds: float

    def config(self) -> dict[str, Any]:
        """Flat scalars only. A nested config is a config ARIA cannot plot."""
        return {
            **self.setup.fields(),
            "rulepack_version": self.result.rulepack_version,
            "cases": len(self.result.outcomes),
        }

    def metrics(self) -> dict[str, Any]:
        return {**self.result.scores, **self._cost()}

    def _cost(self) -> dict[str, Any]:
        fixes = [o.fix for o in self.result.outcomes if o.fix is not None]
        cases = len(self.result.outcomes) or 1
        return {
            "wall_seconds": round(self.wall_seconds, 2),
            "seconds_per_case": round(self.wall_seconds / cases, 3),
            "candidates_measured": sum(fix.measured for fix in fixes),
            "fixes_attempted": len(fixes),
            "fixes_found": sum(1 for fix in fixes if fix.found),
            "cases_failed": len(self.result.failures),
            "completed": self.result.completed,
        }

    def table_rows(self) -> list[list[Any]]:
        return [
            [_cell(row.get(column)) for column in TABLE_COLUMNS]
            for row in self.result.rows()
        ]


def _cell(value: Any) -> Any:
    """A table cell is a number, a string or nothing."""
    if isinstance(value, (list, tuple, set, frozenset)):
        return ", ".join(str(item) for item in sorted(value))
    return value


def grid(**axes: tuple[Any, ...]) -> list[Setup]:
    """Every combination of the given knobs, each named after what it sets."""
    names = list(axes)
    return [
        setup(**dict(zip(names, values)))
        for values in itertools.product(*(axes[name] for name in names))
    ]


DEFAULT_GRID = tuple(grid(**GRID_AXES))


def run_experiment(
    configuration: Setup, cases: list[Case] | None = None
) -> Experiment:
    """One configuration against every case, timed."""
    started = time.monotonic()
    result = evaluate(
        measure=measurements(configuration.measurements),
        rules=load_pack(),
        ledger=ledger(configuration.preview_unverified),
        router=router(configuration.router),
        cases=cases,
        run_fixes=configuration.run_fixes,
        fix_candidates=configuration.fix_candidates,
        publish=False,
    )
    return Experiment(configuration, result, time.monotonic() - started)


def run_grid(
    setups: list[Setup] | tuple[Setup, ...] | None = None,
    *,
    cases: list[Case] | None = None,
) -> list[Experiment]:
    picked = list(cases if cases is not None else dataset())
    return [
        run_experiment(configuration, picked)
        for configuration in (setups if setups is not None else DEFAULT_GRID)
    ]


def target(
    project: str | None = None, entity: str | None = None
) -> tuple[str, str | None] | None:
    """The project ARIA reads, or nothing when there is no account to read it.

    `WANDB_PROJECT` holds either a name or `entity/name`, because that is what
    `weave.init` takes and the two share one project.
    """
    name = project or os.environ.get(PROJECT_ENV)
    if not name or not os.environ.get(KEY_ENV):
        return None
    team = entity or os.environ.get(ENTITY_ENV)
    if "/" in name:
        team, name = name.split("/", 1)
    return name, team


def log_experiments(
    experiments: list[Experiment],
    *,
    project: str | None = None,
    entity: str | None = None,
    group: str = GROUP,
) -> list[str]:
    """One W&B run per configuration. Returns the URL of each.

    Every failure here is a third party's: no account, no network, a rejected
    key, an SDK that moved. None of them may discard numbers that have already
    been computed, so a failure is logged and the local record stands.
    """
    where = target(project, entity)
    if where is None:
        return []
    module = _wandb()
    urls = []
    for experiment in experiments:
        url = _log_one(module, experiment, where, group)
        if url:
            urls.append(url)
    return urls


def _log_one(
    module: Any, experiment: Experiment, where: tuple[str, str | None], group: str
) -> str | None:
    name, team = where
    try:
        run = module.init(
            project=name,
            entity=team,
            name=experiment.setup.label,
            group=group,
            job_type=JOB_TYPE,
            tags=list(TAGS),
            config=experiment.config(),
            notes=NOTES,
            reinit=True,
        )
    except Exception as error:
        log.warning("this configuration stayed local, %s said: %s", name, error)
        return None
    run.log(
        {
            **experiment.metrics(),
            "cases": module.Table(
                columns=list(TABLE_COLUMNS), data=experiment.table_rows()
            ),
        }
    )
    url = getattr(run, "url", None)
    run.finish()
    return url


def save_experiments(experiments: list[Experiment], path: Path) -> Path:
    """The grid on disk, one object per configuration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "lower_is_better": sorted(LOWER_IS_BETTER),
                "runs": [
                    {
                        "label": experiment.setup.label,
                        "config": experiment.config(),
                        "metrics": experiment.metrics(),
                        "failures": experiment.result.failures,
                    }
                    for experiment in experiments
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _wandb() -> Any:
    try:
        import wandb
    except ImportError as error:
        raise RuntimeError(
            "The experiment grid needs: "
            "python -m pip install -e 'packages/agents[observability]'"
        ) from error
    return wandb


__all__ = [
    "DEFAULT_GRID", "GRID_AXES", "GROUP", "JOB_TYPE", "KEY_ENV", "NOTES",
    "TABLE_COLUMNS", "TAGS", "Experiment", "grid", "log_experiments",
    "run_experiment", "run_grid", "save_experiments", "target",
]
