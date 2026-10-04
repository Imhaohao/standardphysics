"""Which cells under a raised piece ADA 2010 306 counts, and the two questions allowed to count them."""

from __future__ import annotations

import math
import uuid

import numpy as np
import pytest
from standardphysics_contracts import (
    Mat4,
    Scenario,
    SceneGraph,
    SceneNode,
    SpaceBeneath,
    Stop,
    Vec3,
    to_inches,
    to_meters,
)
from standardphysics_fixtures.scanned_furniture import MeshSketch, ScannedTable
from standardphysics_pipeline import PipelineMeasurements
from standardphysics_pipeline.floor_coverage import encode_cells, faces_in_room
from standardphysics_pipeline.knee_and_toe import (
    HEIGHT_NOISE,
    KneeAndToeLimits,
    counted_cells,
    credits_for,
    freed_toward,
    wide_enough,
)
from standardphysics_pipeline.occupancy import CELL_SIZE, build_grid
from standardphysics_pipeline.space_beneath import encode_centimetres, measure_space_beneath

LIMITS = KneeAndToeLimits(
    toe_top=to_meters(9.0),
    toe_deepest=to_meters(25.0),
    toe_past_knee=to_meters(6.0),
    knee_top=to_meters(27.0),
    knee_deepest=to_meters(25.0),
    knee_reduction=1.0 / 6.0,
    narrowest=to_meters(30.0),
)
"""306's numbers, as the rule pack holds them for `turning_space`."""

TOP = to_meters(29.5)
FRONT, BACK = 0, 1
DEEPEST_CELLS = int(to_meters(25.0) / CELL_SIZE)
"""25 inches is 25.4 cells, and only whole cells count."""


def _beneath(open_to: np.ndarray, seen: np.ndarray | None = None) -> SpaceBeneath:
    """A record as ingest would store it, for a piece whose heights the test sets cell by cell."""
    rows, columns = open_to.shape
    return SpaceBeneath(
        cell_size=CELL_SIZE, columns=columns, rows=rows,
        floor_seen=encode_cells(np.ones((rows, columns), dtype=bool) if seen is None else seen),
        open_cm=encode_centimetres(open_to), mesh_sha256="0" * 64, method=1,
    )


def _open(rows: int = 48, columns: int = 48) -> np.ndarray:
    """A piece open from the floor to its top all the way across."""
    return np.full((rows, columns), TOP)


def _reads(inches: float) -> float:
    """The lowest whole-centimetre reading that still counts as `inches` once the noise is taken off."""
    return math.ceil((to_meters(inches) + HEIGHT_NOISE) * 100) / 100


def _depth_from_front(open_to: np.ndarray, seen: np.ndarray | None = None, assumed_clear: bool = False) -> int:
    counted = counted_cells(_beneath(open_to, seen), LIMITS, floor_assumed_clear=assumed_clear)[FRONT]
    return int(counted[:, open_to.shape[1] // 2].sum())


def test_an_open_table_counts_25_inches_in_from_each_open_side_and_no_further():
    counted = counted_cells(_beneath(_open()), LIMITS)
    assert counted[FRONT].sum(axis=0).tolist() == [DEEPEST_CELLS] * 48
    assert counted[BACK].sum(axis=0).tolist() == [DEEPEST_CELLS] * 48
    assert not counted[FRONT][DEEPEST_CELLS:].any()


def test_a_panel_hanging_to_24_inches_6_inches_in_holds_the_knee_clearance_to_8_5_and_the_toe_clearance_to_14_5():
    """306.3.4: knee clearance may lose an inch of depth for every 6 inches of height. From 9 inches up to the
    panel's 24 that is 2.5 inches, so 6 inches in plus 2.5 is 8.5 at 9 inches; 306.2.4 lets the toes run 6 past."""
    panel_row = round(to_meters(6.0) / CELL_SIZE)
    open_to = _open()
    open_to[panel_row] = _reads(24.0)
    knee = panel_row * CELL_SIZE + to_meters(24.0 - 9.0) / 6.0
    assert knee == pytest.approx(to_meters(6.0 + 2.5), abs=CELL_SIZE / 2)
    assert _depth_from_front(open_to) == int((knee + to_meters(6.0)) / CELL_SIZE)
    assert _depth_from_front(open_to) * CELL_SIZE == pytest.approx(to_meters(14.5), abs=CELL_SIZE)


@pytest.mark.parametrize(("hangs_to", "leans_back"), [(9.0, 0.0), (15.0, 1.0), (21.0, 2.0), (26.0, 17.0 / 6.0)])
def test_the_knee_clearance_leans_back_an_inch_for_every_6_inches_the_lowest_surface_stands_over_9(hangs_to, leans_back):
    """The mesh reads in whole centimetres, so the surface sits up to a centimetre above `hangs_to`."""
    edge_row = 10
    open_to = _open()
    open_to[edge_row] = _reads(hangs_to)
    lean = (_reads(hangs_to) - HEIGHT_NOISE - to_meters(9.0)) / 6.0
    assert lean == pytest.approx(to_meters(leans_back), abs=0.01 / 6.0)
    reach = edge_row * CELL_SIZE + lean + to_meters(6.0)
    assert _depth_from_front(open_to) == int(reach / CELL_SIZE + 1e-9)


def test_a_surface_at_27_inches_or_higher_limits_nothing():
    open_to = _open()
    open_to[5] = _reads(27.0)
    assert _depth_from_front(open_to) == DEEPEST_CELLS


def test_a_crossbar_in_the_toe_band_stops_the_count_where_it_stands():
    open_to = _open()
    open_to[8] = to_meters(4.0)
    assert _depth_from_front(open_to) == 8


def test_an_apron_lower_than_27_inches_at_the_edge_leaves_no_knee_clearance_on_that_side():
    open_to = _open()
    open_to[0] = _reads(26.0)
    counted = counted_cells(_beneath(open_to), LIMITS)
    assert not counted[FRONT].any()
    assert counted[BACK].sum(axis=0).max() == DEEPEST_CELLS


@pytest.mark.parametrize(("opening_cells", "counts"), [(26, False), (30, False), (31, True)])
def test_an_opening_under_30_inches_wide_counts_nothing(opening_cells, counts):
    """30 inches is 30.48 cells, so 31 whole cells is the narrowest opening that counts."""
    open_to = np.full((48, 60), to_meters(1.0))
    start = (60 - opening_cells) // 2
    open_to[:, start:start + opening_cells] = TOP
    assert counted_cells(_beneath(open_to), LIMITS)[FRONT].any() == counts


def test_floor_the_scan_missed_counts_only_when_it_is_assumed_clear():
    seen = np.ones((48, 48), dtype=bool)
    seen[4:] = False
    assert _depth_from_front(_open(), seen) == 4
    assert _depth_from_front(_open(), seen, assumed_clear=True) == DEEPEST_CELLS


def test_a_record_with_no_floor_seen_at_its_edge_counts_nothing():
    seen = np.ones((48, 48), dtype=bool)
    seen[0] = False
    assert _depth_from_front(_open(), seen) == 0


def test_a_run_of_lanes_counts_whole_at_either_end_of_the_grid():
    row = np.zeros((1, 12), dtype=bool)
    row[0, :4] = True
    row[0, 8:] = True
    assert wide_enough(row, 4).tolist() == row.tolist()
    assert not wide_enough(row, 5).any()


ROOM = 5.0


def _floor_node() -> SceneNode:
    return SceneNode(
        id=uuid.uuid5(uuid.NAMESPACE_URL, "knee floor"), kind="floor", label="Floor", raw_category="floor",
        dimensions=Vec3(x=ROOM, y=ROOM, z=0.01), transform=Mat4.translation(0.0, 0.0, 0.0),
    )


def _box(name: str, low: tuple[float, float, float], high: tuple[float, float, float], label: str = "") -> SceneNode:
    size = [b - a for a, b in zip(low, high, strict=True)]
    middle = [(a + b) / 2 for a, b in zip(low, high, strict=True)]
    return SceneNode(
        id=uuid.uuid5(uuid.NAMESPACE_URL, name), kind="object", label=label or name, raw_category="storage",
        dimensions=Vec3(x=size[0], y=size[1], z=size[2]), transform=Mat4.translation(*middle),
    )


def _room(table: ScannedTable, *others: SceneNode, unseen=()) -> SceneGraph:
    """A floor, the table drawn into a mesh with the floor around and under it, and whatever else stands there."""
    sketch = table.drawn(MeshSketch().floor((-ROOM / 2, -ROOM / 2, ROOM / 2, ROOM / 2), unseen=unseen))
    graph = SceneGraph(
        scan_id=uuid.uuid4(), nodes=[_floor_node(), table.node(), *others], capture_to_room=Mat4.identity()
    )
    return measure_space_beneath(graph, faces_in_room(sketch.mesh(), graph.capture_to_room), "0" * 64)


DEEP_TABLE = ScannedTable("Deep table", (0.0, 0.0), width=2.0, depth=1.6, height=TOP)
"""63 inches deep, so what counts from one long side never meets what counts from the other."""


def test_a_circle_in_front_of_a_table_reaches_25_inches_under_it():
    graph = _room(DEEP_TABLE)
    edge = -DEEP_TABLE.depth / 2
    at = Vec3(x=0.0, y=edge - 0.4, z=0.0)
    measure = PipelineMeasurements()
    plain = measure.turning_space(graph, at)
    counted = measure.turning_space_with_knee_and_toe(graph, at, LIMITS)
    assert plain.inches_wide == pytest.approx(2 * 0.4 / 0.0254, abs=2.0)
    assert counted.space.inches_wide == pytest.approx(2 * (0.4 + DEEPEST_CELLS * CELL_SIZE) / 0.0254, abs=2.0)
    assert counted.under == (DEEP_TABLE.node().id,)
    assert counted.if_seen is None


def test_a_circle_never_sits_under_the_table():
    graph = _room(DEEP_TABLE)
    measure = PipelineMeasurements()
    counted = measure.turning_space_with_knee_and_toe(graph, Vec3(x=0.0, y=0.0, z=0.0), LIMITS)
    assert counted.space.inches_wide == 0.0
    assert counted.under == ()


def test_a_circle_reaches_in_only_from_the_side_it_stands_outside():
    graph = _room(DEEP_TABLE)
    grid = build_grid(graph)
    credits = credits_for(graph, grid, LIMITS)
    [front] = freed_toward(credits, Vec3(x=0.0, y=-1.5, z=0.0))
    [back] = freed_toward(credits, Vec3(x=0.0, y=1.5, z=0.0))
    middle_row = int((0.0 - grid.origin_y) / CELL_SIZE) - front.rows.start
    assert front.cells[:middle_row].any() and not front.cells[middle_row:].any()
    assert back.cells[middle_row:].any() and not back.cells[:middle_row].any()


def test_cells_another_piece_stands_on_stay_occupied():
    bin_under = _box("Bin", (-0.2, -0.6, 0.0), (0.2, -0.3, 0.5), "Bin")
    graph = _room(DEEP_TABLE, bin_under)
    grid = build_grid(graph)
    [front] = freed_toward(credits_for(graph, grid, LIMITS), Vec3(x=0.0, y=-1.5, z=0.0))
    row, column = grid.to_cell(0.0, -0.45)
    assert grid.occupied[row, column]
    assert not front.cells[row - front.rows.start, column - front.columns.start]


def test_unseen_floor_under_the_table_counts_only_toward_what_another_look_could_settle():
    graph = _room(DEEP_TABLE, unseen=(DEEP_TABLE.footprint,))
    edge = -DEEP_TABLE.depth / 2
    at = Vec3(x=0.0, y=edge - 0.4, z=0.0)
    measure = PipelineMeasurements()
    counted = measure.turning_space_with_knee_and_toe(graph, at, LIMITS)
    assert counted.space == measure.turning_space(graph, at)
    assert counted.under == ()
    assert counted.if_seen is not None and counted.if_seen.inches_wide > counted.space.inches_wide + 40
    assert counted.unseen_under == (DEEP_TABLE.node().id,)


def test_route_widths_never_count_the_space_under_a_table():
    """403.5.1 grants no knee and toe clearance, so the evidence changes nothing about a route.

    The only way east runs between a shelf and the table's south edge, 27.6 inches apart. Shelves either
    side of the table stand further back, so the table alone pinches it, and counting the 25 inches under
    the table would have widened it.
    """
    table = ScannedTable("Table", (0.0, 0.0), width=2.0, depth=1.2, height=TOP)
    stops = [Stop(name="Entrance", position=Vec3(x=-2.0, y=-1.0, z=0.0)), Stop(name="Seats", position=Vec3(x=2.0, y=-1.0, z=0.0))]
    scenario = Scenario(stops=stops)
    south = _box("South shelf", (-2.6, -1.5, 0.0), (2.6, -1.3, 2.0), "Shelf")
    west = _box("West shelf", (-2.6, -0.2, 0.0), (-1.0, 2.6, 2.0), "Shelf")
    east = _box("East shelf", (1.0, -0.2, 0.0), (2.6, 2.6, 2.0), "Shelf")
    measured = _room(table, south, west, east)
    bare = measured.model_copy(update={"nodes": [node.model_copy(update={"space_beneath": None}) for node in measured.nodes]})
    with_evidence = PipelineMeasurements().route_clear_width(measured, scenario, 0)
    without = PipelineMeasurements().route_clear_width(bare, scenario, 0)
    assert with_evidence == without
    assert with_evidence.inches == pytest.approx(to_inches(1.3 - table.depth / 2), abs=0.5)


def test_the_clear_floor_at_a_counter_counts_the_table_it_backs_onto():
    """The counter's face is 27 inches from the table, 3 short of the 30 inch depth, and the table's 25 inches cover it."""
    counter = _box("Counter", (-1.0, 0.9, 0.0), (1.0, 1.5, 0.9), "Counter")
    table = ScannedTable("Table", (0.0, 0.9 - to_meters(27.0) - 0.4), width=2.0, depth=0.8, height=TOP)
    graph = _room(table, counter)
    measure = PipelineMeasurements()
    plain = measure.counter_approach(graph, counter.id, slide_meters=0.0)
    counted = measure.counter_approach_with_knee_and_toe(graph, counter.id, 0.0, LIMITS)
    assert not plain.fits and plain.inches_deep < 30.0
    assert counted.space.fits
    assert counted.under == (table.node().id,)


def test_a_turned_table_frees_the_same_space_from_its_long_side():
    """Turned a quarter, the table's long sides face east and west, and a circle west of it reaches the same 25 inches."""
    quarter_turn = Mat4(m=[0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1, TOP / 2, 0, 0, 0, 1])
    turned = DEEP_TABLE.node().model_copy(update={"transform": quarter_turn})
    as_drawn = ScannedTable(DEEP_TABLE.name, (0.0, 0.0), width=DEEP_TABLE.depth, depth=DEEP_TABLE.width, height=TOP)
    sketch = as_drawn.drawn(MeshSketch().floor((-ROOM / 2, -ROOM / 2, ROOM / 2, ROOM / 2)))
    graph = SceneGraph(scan_id=uuid.uuid4(), nodes=[_floor_node(), turned], capture_to_room=Mat4.identity())
    graph = measure_space_beneath(graph, faces_in_room(sketch.mesh(), graph.capture_to_room), "0" * 64)
    at = Vec3(x=-DEEP_TABLE.depth / 2 - 0.4, y=0.0, z=0.0)
    counted = PipelineMeasurements().turning_space_with_knee_and_toe(graph, at, LIMITS)
    assert counted.space.inches_wide == pytest.approx(2 * (0.4 + DEEPEST_CELLS * CELL_SIZE) / 0.0254, abs=2.0)
    assert counted.under == (turned.id,)
