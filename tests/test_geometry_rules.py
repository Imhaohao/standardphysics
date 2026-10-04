"""The browser's copy of the layout rules is the one the Python modules would write today.

apps/web/src/types/geometry-rules.ts holds every tolerance and limit the
workspace checks a dragged piece against before the server sees it. A
constant changed in Python and not regenerated would leave the browser sliding
pieces by the old number, so these fail until `npm run contracts` has been run
in apps/web. CI's contracts job regenerates the file and diffs it too.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from standardphysics_agents.fix import constraints, geometry_rules, moves
from standardphysics_fixtures import build_graph

ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATED = ROOT / "apps" / "web" / "src" / "types" / "geometry-rules.ts"
NUMBER = re.compile(r"^export const (\w+) = (-?[\d.e+-]+);$", re.MULTILINE)


def test_the_committed_rules_are_what_the_python_constants_generate():
    assert GENERATED.read_text(encoding="utf-8") == geometry_rules.typescript(), (
        "a shared constant changed: run `npm run contracts` in apps/web and commit geometry-rules.ts"
    )


@pytest.mark.parametrize(("module", "name", "changed"), [
    (constraints, "OVERLAP_TOLERANCE", 0.006),
    (constraints, "SWING_KINDS", frozenset({"door", "gate"})),
    (moves, "RESTING_GAP", 0.15),
])
def test_changing_a_constant_without_regenerating_is_caught(monkeypatch, module, name, changed):
    monkeypatch.setattr(module, name, changed)
    assert GENERATED.read_text(encoding="utf-8") != geometry_rules.typescript()


def test_every_number_reaches_the_browser_exactly():
    written = {name: float(literal) for name, literal in NUMBER.findall(GENERATED.read_text(encoding="utf-8"))}
    numbers = {shared.name: shared.value for shared in geometry_rules.SHARED if isinstance(shared.value, int | float)}
    assert written == numbers


def test_the_keep_clear_square_is_built_from_the_door_sweep_constants(monkeypatch):
    door = next(node for node in build_graph().nodes if node.kind == "door")
    square = constraints.door_keep_clear(door)
    monkeypatch.setattr(constraints, "DOOR_SWEEP_ACROSS", 2 * constraints.DOOR_SWEEP_ACROSS)
    assert _span(constraints.door_keep_clear(door)) == pytest.approx(2 * _span(square))


def _span(polygon) -> float:
    xs, ys = [x for x, _ in polygon], [y for _, y in polygon]
    return max(max(xs) - min(xs), max(ys) - min(ys))
