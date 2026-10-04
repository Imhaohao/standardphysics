"""Turning space and clear floor space may count knee and toe clearance; nothing else may.

Every scene is one small restroom, 3 by 2 metres inside four walls, with a
table pushed against the north wall. The open floor south of the table is
`gap` inches deep, so a 60 inch circle there has to reach 60 minus `gap`
inches under the table, and only 306's knee and toe clearance can give it that.
"""

from __future__ import annotations

import uuid

import pytest
from standardphysics_agents.checks import CheckContext, route_clear_width, turning_space
from standardphysics_agents.checks.knee_and_toe import limits
from standardphysics_agents.checks.observation import Observation
from standardphysics_agents.checks.restroom import restroom_turning_space
from standardphysics_agents.checks.service_counter import service_counter_approach
from standardphysics_agents.copy import FindingCopy
from standardphysics_agents.findings import to_finding
from standardphysics_agents.knee_copy import look_underneath, with_counted_floor
from standardphysics_contracts import Mat4, Scenario, SceneGraph, SceneNode, Stop, Vec3, to_meters
from standardphysics_fixtures import FixtureMeasurements
from standardphysics_fixtures.scanned_furniture import MeshSketch, ScannedTable
from standardphysics_pipeline import PipelineMeasurements
from standardphysics_pipeline.floor_coverage import faces_in_room
from standardphysics_pipeline.space_beneath import measure_space_beneath

INSIDE = (-1.5, -1.0, 1.5, 1.0)
"""The floor, wall to wall."""

SOUTH_FACE = -0.95
"""Where the south wall's cells start: the grid draws a wall 10 cm thick about its line."""

NORTH_FACE = 0.95
TOP = to_meters(29.5)


def _node(name: str, kind: str, centre: tuple[float, float, float], size: tuple[float, float, float]) -> SceneNode:
    return SceneNode(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"knee {name}"), kind=kind, label=name, raw_category=kind,
        dimensions=Vec3(x=size[0], y=size[1], z=size[2]), transform=Mat4.translation(*centre),
    )


def _shell() -> list[SceneNode]:
    x0, y0, x1, y1 = INSIDE
    return [
        _node("Floor", "floor", (0.0, 0.0, 0.0), (x1 - x0, y1 - y0, 0.01)),
        _node("South wall", "wall", (0.0, y0, 1.2), (x1 - x0, 0.04, 2.4)),
        _node("North wall", "wall", (0.0, y1, 1.2), (x1 - x0, 0.04, 2.4)),
        _node("West wall", "wall", (x0, 0.0, 1.2), (0.04, y1 - y0, 2.4)),
        _node("East wall", "wall", (x1, 0.0, 1.2), (0.04, y1 - y0, 2.4)),
    ]


def _table(gap: float, label: str = "Table", **shape) -> ScannedTable:
    """A table 2 m wide against the north wall, its south edge `gap` inches from the south wall."""
    south = SOUTH_FACE + to_meters(gap)
    return ScannedTable(label, (0.0, (south + NORTH_FACE) / 2), width=2.0, depth=NORTH_FACE - south, height=TOP, **shape)


def _scene(table: ScannedTable, *extra: SceneNode, sketch: MeshSketch | None = None, drawn: bool = True,
           unseen: tuple = ()) -> SceneGraph:
    """The restroom with the table in it, measured from a mesh of its floor and the table."""
    mesh = (sketch or MeshSketch()).floor(INSIDE, unseen=unseen)
    if drawn:
        table.drawn(mesh)
    graph = SceneGraph(
        scan_id=uuid.uuid5(uuid.NAMESPACE_URL, "knee room"), nodes=[*_shell(), table.node(), *extra],
        capture_to_room=Mat4.identity(),
    )
    return measure_space_beneath(graph, faces_in_room(mesh.mesh(), graph.capture_to_room), "0" * 64)


STOP_Y = SOUTH_FACE + to_meters(30.5)
"""Half an inch further from the south wall than a 60 inch circle's radius."""


def _scenario() -> Scenario:
    return Scenario(name="Use the restroom", stops=[
        Stop(name="Entrance", position=Vec3(x=-1.2, y=STOP_Y, z=0.0)),
        Stop(name="Restroom", position=Vec3(x=0.0, y=STOP_Y, z=0.0)),
        Stop(name="Exit", position=Vec3(x=-1.2, y=STOP_Y, z=0.0)),
    ])


def _ctx(graph: SceneGraph, pack, ledger, measure=None) -> CheckContext:
    return CheckContext(graph, _scenario(), measure or PipelineMeasurements(), pack, ledger)


def _turn(graph: SceneGraph, pack, ledger, measure=None):
    [observation] = turning_space(_ctx(graph, pack, ledger, measure))
    return observation


def _finding(observation, graph, pack):
    return to_finding(observation, pack.by_id(observation.rule_id), graph, graph.scan_id)


def test_a_table_on_four_thin_legs_over_seen_floor_completes_the_turning_circle(pack, ledger):
    table = _table(52.0)
    graph = _scene(table)
    observation = _turn(graph, pack, ledger)
    finding = _finding(observation, graph, pack)
    assert observation.satisfied and observation.measured_inches >= 60.0
    assert observation.facts["under"] == ["Table"]
    assert observation.relied_on == (table.node().id,)
    assert finding.outcome == "passes"
    assert "That counts the floor under the table" in finding.detail
    assert "Keep that floor clear." in finding.detail
    assert table.node().id in finding.locus.node_ids


def _bare(graph: SceneGraph) -> SceneGraph:
    """The same room as a scan with no mesh would leave it."""
    return graph.model_copy(update={"nodes": [node.model_copy(update={"space_beneath": None}) for node in graph.nodes]})


def test_without_the_space_under_the_table_the_same_circle_does_not_fit(pack, ledger):
    """The plain grid is what every other question sees, and 52 inches of floor hold no 60 inch circle."""
    plain = _turn(_bare(_scene(_table(52.0))), pack, ledger)
    assert not plain.satisfied and plain.measured_inches < 52.0


def test_a_solid_cabinet_gives_nothing(pack, ledger):
    cabinet = _table(52.0, label="Cabinet")
    x0, y0, x1, y1 = cabinet.footprint
    graph = _scene(cabinet, sketch=MeshSketch().box((x0, y0, 0.0), (x1, y1, TOP)), drawn=False)
    observation = _turn(graph, pack, ledger)
    assert not observation.satisfied
    assert observation.facts["under"] == [] and observation.facts["look_under"] == []
    assert _finding(observation, graph, pack).outcome == "problem"


def _panel(table: ScannedTable, inches_in: float, hangs_to: float) -> MeshSketch:
    """A modesty panel across the table, `inches_in` from its open south edge, hanging from the top to `hangs_to`."""
    x0, y0, x1, _ = table.footprint
    south = y0 + to_meters(inches_in)
    return MeshSketch().box((x0, south, to_meters(hangs_to)), (x1, south + 0.02, table.underside))


@pytest.mark.parametrize(("gap", "fits"), [(52.0, True), (42.0, False)])
def test_a_modesty_panel_hanging_to_24_inches_holds_the_count_to_14_and_a_half_inches(pack, ledger, gap, fits):
    """6 inches in, the panel limits knee clearance to 8.5 inches and toe clearance to 14.5 (306.3.4, 306.2.4).
    A 52 inch gap needs 8 of them and a 42 inch gap needs 18, which an open table would still give."""
    counter = _table(gap, label="Counter")
    graph = _scene(counter, sketch=_panel(counter, 6.0, 24.0))
    assert _turn(graph, pack, ledger).satisfied == fits
    assert _turn(_scene(_table(gap)), pack, ledger).satisfied


def test_a_panel_lower_than_27_inches_at_the_open_edge_leaves_no_knee_clearance(pack, ledger):
    counter = _table(52.0, label="Counter")
    graph = _scene(counter, sketch=_panel(counter, 0.0, 24.0))
    assert not _turn(graph, pack, ledger).satisfied


def test_floor_the_scan_missed_under_the_table_asks_for_another_look(pack, ledger):
    table = _table(52.0)
    graph = _scene(table, unseen=(table.footprint,))
    observation = _turn(graph, pack, ledger)
    finding = _finding(observation, graph, pack)
    assert not observation.satisfied
    assert observation.facts["look_under"] == ["Table"]
    assert finding.outcome == "question" and finding.asks == "another_look"
    assert finding.title == "Point the phone under the table again"
    assert finding.fix is None


def test_floor_the_scan_missed_asks_nothing_when_the_circle_fits_without_it(pack, ledger):
    table = _table(62.0)
    graph = _scene(table, unseen=(table.footprint,))
    observation = _turn(graph, pack, ledger)
    assert observation.satisfied
    assert observation.facts["look_under"] == [] and observation.facts["under"] == []
    assert _finding(observation, graph, pack).outcome == "passes"


def test_floor_the_scan_missed_never_settles_a_space_that_falls_short_either_way(pack, ledger):
    """A 33 inch gap needs 27 inches under the table, past the 25 inches 306 ever counts, seen or not."""
    table = _table(33.0)
    graph = _scene(table, unseen=(table.footprint,))
    observation = _turn(graph, pack, ledger)
    assert not observation.satisfied
    assert _finding(observation, graph, pack).outcome == "problem"


def test_an_opening_26_inches_wide_under_the_table_gives_nothing(pack, ledger):
    narrow = _table(57.0, legs_apart=to_meters(26.0))
    assert not _turn(_scene(narrow), pack, ledger).satisfied
    assert _turn(_scene(_table(57.0)), pack, ledger).satisfied


@pytest.mark.parametrize(("gap", "fits"), [(38.0, True), (33.0, False)])
def test_no_more_than_25_inches_under_the_table_ever_counts(pack, ledger, gap, fits):
    """A 38 inch gap needs 22 inches under the table and a 33 inch gap needs 27, past 306.2.2 and 306.3.2."""
    assert _turn(_scene(_table(gap)), pack, ledger).satisfied == fits


def test_the_restroom_turning_space_counts_the_table_too(pack, ledger):
    toilet = _node("Toilet", "toilet", (-1.25, -0.65, 0.2), (0.4, 0.55, 0.4))
    graph = _scene(_table(47.0), toilet)
    [observation] = restroom_turning_space(_ctx(graph, pack, ledger))
    assert observation.satisfied
    assert observation.facts["under"] == ["Table"]
    assert _finding(observation, graph, pack).outcome == "passes"


def test_route_widths_never_count_the_space_under_the_table(pack, ledger):
    graph = _scene(_table(52.0))
    measured = route_clear_width(_ctx(graph, pack, ledger))
    without = route_clear_width(_ctx(_bare(graph), pack, ledger))
    assert measured and [(o.measured_inches, o.satisfied) for o in measured] == [
        (o.measured_inches, o.satisfied) for o in without
    ]


def test_the_counter_clear_floor_counts_a_table_behind_it(pack, ledger):
    """The counter's face is 27 inches from a table, 3 short of the 30 inch depth; the table's 25 cover it."""
    table = ScannedTable("Table", (0.0, -0.55), width=2.0, depth=0.8, height=TOP)
    face = table.footprint[3] + to_meters(27.0)
    counter = _node("Counter", "counter", (0.0, face + 0.3, 0.45), (2.4, 0.6, 0.9))
    graph = _scene(table, counter)
    [observation] = service_counter_approach(_ctx(graph, pack, ledger))
    assert observation.satisfied
    assert observation.facts["under"] == ["Table"]
    assert table.node().id in observation.relied_on
    assert "That counts the floor under the table" in _finding(observation, graph, pack).detail


def test_a_provider_that_cannot_count_knee_room_answers_on_the_plain_grid(pack, ledger):
    graph = _scene(_table(52.0))
    observation = _turn(graph, pack, ledger, FixtureMeasurements())
    assert observation.facts["under"] == [] and observation.asks_for is None


def test_the_rule_pack_numbers_reach_the_measurement_in_metres(pack, ledger):
    allowed = limits(_ctx(_scene(_table(52.0)), pack, ledger))
    assert allowed.toe_top == pytest.approx(to_meters(9.0))
    assert allowed.knee_top == pytest.approx(to_meters(27.0))
    assert allowed.toe_deepest == allowed.knee_deepest == pytest.approx(to_meters(25.0))
    assert allowed.toe_past_knee == pytest.approx(to_meters(6.0))
    assert allowed.knee_reduction == pytest.approx(1.0 / 6.0)
    assert allowed.narrowest == pytest.approx(to_meters(30.0))


def test_two_pieces_are_named_together_and_spoken_of_as_them():
    counted = with_counted_floor(
        FindingCopy(title="There's room", detail="The clear floor is 61 inches across."),
        Observation(rule_id="turning_space", satisfied=True, facts={"under": ["Table", "Desk"]}),
    )
    assert counted.detail.endswith(
        "That counts the floor under the table and the desk, because a wheelchair user's feet and knees fit under "
        "them. Keep that floor clear."
    )
    asked = look_underneath(["Table", "Table"])
    assert asked.title == "Point the phone under the two tables again"
    assert "the floor under them" in asked.detail
