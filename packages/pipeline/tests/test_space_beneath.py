"""What the mesh saw under a raised piece, read once at ingest and stored in the piece's own frame."""

from __future__ import annotations

import json
import uuid

import numpy as np
import pytest
from standardphysics_contracts import Mat4, SceneGraph, SceneNode, SurfaceHeight, Vec3, to_meters
from standardphysics_fixtures.scanned_furniture import MeshSketch, ScannedTable
from standardphysics_pipeline.floor_coverage import FLOOR_BAND, decode_cells, faces_in_room
from standardphysics_pipeline.occupancy import CELL_SIZE
from standardphysics_pipeline.space_beneath import (
    THINNEST_TOP,
    decode_centimetres,
    encode_centimetres,
    measure_space_beneath,
    with_mesh_evidence,
)

SHA = "b" * 64
TABLE = ScannedTable("Table", (0.0, 0.0), width=1.2, depth=0.8, height=to_meters(29.5))


def _floor() -> SceneNode:
    return SceneNode(
        id=uuid.uuid5(uuid.NAMESPACE_URL, "floor"), kind="floor", label="Floor", raw_category="floor",
        dimensions=Vec3(x=4.0, y=4.0, z=0.01), transform=Mat4.translation(0.0, 0.0, 0.0),
    )


def _measured(sketch: MeshSketch, *pieces: SceneNode) -> SceneGraph:
    graph = SceneGraph(scan_id=uuid.uuid4(), nodes=[_floor(), *pieces], capture_to_room=Mat4.identity())
    return measure_space_beneath(graph, faces_in_room(sketch.mesh(), graph.capture_to_room), SHA)


def _grids(graph: SceneGraph, piece: SceneNode) -> tuple[np.ndarray, np.ndarray]:
    beneath = graph.by_id(piece.id).space_beneath
    assert beneath is not None
    return (
        decode_cells(beneath.floor_seen, beneath.rows, beneath.columns),
        decode_centimetres(beneath.open_cm, beneath.rows, beneath.columns),
    )


def _cell(x: float, y: float, table: ScannedTable = TABLE) -> tuple[int, int]:
    """The row and column of the piece's grid over a room point, for a table that is not turned."""
    x0, y0, _, _ = table.footprint
    return int((y - y0) / CELL_SIZE), int((x - x0) / CELL_SIZE)


def test_a_table_on_legs_shows_seen_floor_under_it_and_its_underside_above():
    graph = _measured(TABLE.drawn(MeshSketch().floor((-2.0, -2.0, 2.0, 2.0))), TABLE.node())
    seen, open_to = _grids(graph, TABLE.node())
    beneath = graph.by_id(TABLE.node().id).space_beneath
    assert (beneath.columns, beneath.rows) == (48, 32)
    middle = _cell(0.0, 0.0)
    assert seen[middle]
    assert open_to[middle] == pytest.approx(TABLE.underside, abs=0.01)
    assert open_to[middle] <= TABLE.underside
    leg = _cell(TABLE.footprint[0] + 0.02, TABLE.footprint[1] + 0.02)
    assert open_to[leg] == pytest.approx(FLOOR_BAND, abs=0.02)


def test_floor_the_mesh_never_saw_is_not_seen():
    hole = (-0.3, -0.2, 0.3, 0.2)
    graph = _measured(TABLE.drawn(MeshSketch().floor((-2.0, -2.0, 2.0, 2.0), unseen=(hole,))), TABLE.node())
    seen, _ = _grids(graph, TABLE.node())
    assert not seen[_cell(0.0, 0.0)]
    assert seen[_cell(0.45, 0.3)]


def test_where_only_the_top_shows_the_space_stops_a_top_thickness_under_it():
    """A centimetre-thin top shows its own underside, but a phone rarely sees one, so the record never
    puts the underside closer than an inch to the top."""
    sketch = MeshSketch().floor((-2.0, -2.0, 2.0, 2.0))
    sketch.box((TABLE.footprint[0], TABLE.footprint[1], TABLE.height - 0.01), (TABLE.footprint[2], TABLE.footprint[3], TABLE.height))
    graph = _measured(sketch, TABLE.node())
    _, open_to = _grids(graph, TABLE.node())
    assert open_to[_cell(0.0, 0.0)] == pytest.approx(TABLE.height - THINNEST_TOP, abs=0.01)
    assert open_to[_cell(0.0, 0.0)] <= TABLE.height - THINNEST_TOP


def test_a_chair_pushed_under_the_table_is_what_the_mesh_shows_under_it():
    sketch = TABLE.drawn(MeshSketch().floor((-2.0, -2.0, 2.0, 2.0)))
    sketch.box((-0.2, -0.4, 0.43), (0.2, -0.05, 0.45))
    graph = _measured(sketch, TABLE.node())
    _, open_to = _grids(graph, TABLE.node())
    assert open_to[_cell(0.0, -0.2)] == pytest.approx(0.43, abs=0.01)


def test_the_measured_top_holds_the_space_down_when_it_is_lower_than_the_box():
    lower = TABLE.node().model_copy(update={"top_surface": SurfaceHeight(height_m=0.60, uncertainty_m=0.02)})
    sketch = MeshSketch().floor((-2.0, -2.0, 2.0, 2.0))
    graph = _measured(sketch, lower)
    _, open_to = _grids(graph, lower)
    assert float(open_to.max()) == pytest.approx(0.60 - THINNEST_TOP, abs=0.01)


def test_walls_and_the_floor_carry_nothing():
    wall = SceneNode(
        id=uuid.uuid5(uuid.NAMESPACE_URL, "wall"), kind="wall", label="Wall", raw_category="wall",
        dimensions=Vec3(x=4.0, y=0.04, z=2.4), transform=Mat4.translation(0.0, 1.9, 1.2),
    )
    graph = _measured(TABLE.drawn(MeshSketch().floor((-2.0, -2.0, 2.0, 2.0))), TABLE.node(), wall)
    assert graph.by_id(wall.id).space_beneath is None
    assert graph.by_id(_floor().id).space_beneath is None


def test_a_turned_table_keeps_its_grid_in_its_own_frame():
    """The table's long side runs along the room's y, so its own x is the room's y and its own y the room's -x."""
    quarter_turn = Mat4(m=[0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1, TABLE.height / 2, 0, 0, 0, 1])
    turned = TABLE.node().model_copy(update={"transform": quarter_turn})
    as_drawn = ScannedTable("Table", (0.0, 0.0), width=TABLE.depth, depth=TABLE.width, height=TABLE.height)
    graph = _measured(as_drawn.drawn(MeshSketch().floor((-2.0, -2.0, 2.0, 2.0))), turned)
    beneath = graph.by_id(turned.id).space_beneath
    _, open_to = _grids(graph, turned)
    assert (beneath.columns, beneath.rows) == (48, 32)
    assert open_to[beneath.rows - 1, 0] == pytest.approx(FLOOR_BAND, abs=0.02)
    assert open_to[beneath.rows // 2, beneath.columns // 2] == pytest.approx(TABLE.underside, abs=0.01)


def test_heights_round_down_to_whole_centimetres_and_come_back_in_metres():
    heights = np.asarray([[0.0, 0.1234, 0.699], [0.70, 1.5, 9.0]])
    decoded = decode_centimetres(encode_centimetres(heights), 2, 3)
    assert decoded.tolist() == [[0.0, 0.12, 0.69], [0.70, 1.5, 2.54]]


def test_one_read_of_the_mesh_measures_the_floor_and_the_space_beneath(tmp_path):
    sketch = TABLE.drawn(MeshSketch().floor((-2.0, -2.0, 2.0, 2.0)))
    path = tmp_path / "lidar-mesh.json"
    path.write_text(json.dumps(sketch.mesh().model_dump(mode="json")))
    graph = SceneGraph(scan_id=uuid.uuid4(), nodes=[_floor(), TABLE.node()], capture_to_room=Mat4.identity())
    measured = with_mesh_evidence(graph, path, SHA)
    assert [coverage.mesh_sha256 for coverage in measured.floor_coverage] == [SHA]
    assert measured.by_id(TABLE.node().id).space_beneath.mesh_sha256 == SHA


def test_an_unreadable_mesh_or_a_graph_with_no_room_frame_is_left_alone(tmp_path):
    graph = SceneGraph(scan_id=uuid.uuid4(), nodes=[_floor(), TABLE.node()], capture_to_room=Mat4.identity())
    missing = tmp_path / "missing.json"
    assert with_mesh_evidence(graph, missing, SHA) == graph
    path = tmp_path / "lidar-mesh.json"
    path.write_text(json.dumps(TABLE.drawn(MeshSketch().floor((-2.0, -2.0, 2.0, 2.0))).mesh().model_dump(mode="json")))
    unplaced = graph.model_copy(update={"capture_to_room": None})
    assert with_mesh_evidence(unplaced, path, SHA) == unplaced
