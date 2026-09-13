"""The reactive notebook still runs, and still runs on the real evaluator.

Nothing else imports `notebooks/scenario_sweep.py`, so a rename in the
evaluation package would break it quietly. marimo executes every cell when the
notebook is run as a program, which is enough to catch a name that moved, a
value defined in two cells, and a cell that references another cell's local.

It also pins the two properties the notebook is built on: the sweep's cache key
does not move when the slider being swept moves, and a knob that sets a
dimension does not claim one the routine took away.
"""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

NOTEBOOK = Path(__file__).resolve().parents[1] / "notebooks" / "scenario_sweep.py"

SWEPT_KNOB = "aisle_inches"


@pytest.fixture(scope="module")
def notebook():
    pytest.importorskip(
        "marimo",
        reason='needs the notebook extra: pip install -e "packages/agents[notebook]"',
    )
    spec = importlib.util.spec_from_file_location("scenario_sweep", NOTEBOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ran(notebook):
    """Every cell, executed. marimo raises if the graph is not sound."""
    return notebook.app.run()[1]


class TestTheNotebookRuns:
    def test_it_measures_the_room_its_sliders_built(self, ran):
        scored = ran["scenarios"].scores(ran["outcome"])
        assert scored["measurement_error_in"] < 0.05

    def test_the_sweep_visited_every_reading(self, ran):
        assert len(ran["sweep"]) == ran["steps"].value

    def test_the_chart_names_itself_for_a_screen_reader(self, ran):
        assert "<title>" in ran["sweep_view"]().text

    def test_the_findings_lead_with_the_plain_sentence(self, ran):
        problems = ran["outcome"].result.problems
        assert problems
        assert problems[0].title in ran["findings_list"](ran["outcome"])


class TestWhatTheNotebookRestsOn:
    def test_moving_the_swept_slider_leaves_the_cache_key_alone(self, ran):
        parked = ran["parked"]
        knobs = ran["knobs"]
        assert parked(knobs, SWEPT_KNOB) == parked(
            replace(knobs, **{SWEPT_KNOB: 58.5}), SWEPT_KNOB
        )

    def test_moving_another_slider_does_not(self, ran):
        parked, knobs = ran["parked"], ran["knobs"]
        assert parked(knobs, SWEPT_KNOB) != parked(
            replace(knobs, counter_inches=34.0), SWEPT_KNOB
        )

    def test_a_routine_that_crosses_the_doorway_cites_nothing(self, ran):
        """The doorway becomes the pinch, so 403.5.1 on an aisle axis would be
        pointing at the wrong dimension."""
        street = replace(ran["knobs"], routine="street")
        assert ran["scenarios"].PINS[SWEPT_KNOB] not in ran["scenarios"].expected_inches(
            street
        )

    def test_every_knob_has_a_name_and_a_range(self, ran):
        for knob, (name, lowest, highest, step) in ran["KNOBS"].items():
            assert knob in ran["scenarios"].PINS
            assert name and lowest < highest and step > 0
