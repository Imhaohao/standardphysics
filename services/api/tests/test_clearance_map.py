"""The clearance map: every point's clear width, read off the grid a drag check measures the same layout on."""

import base64
import io
import uuid

import numpy as np
import pytest
from PIL import Image
from standardphysics_agents.rules.pack import COMPARISON_EPSILON
from standardphysics_contracts import NodeMove, Scenario, SceneGraph, to_inches, to_meters
from standardphysics_fixtures import node_id
from standardphysics_pipeline.occupancy import build_grid
from standardphysics_pipeline.routes import clearance_map, widest_path

from conftest import drain
from standardphysics_api import repository_revisions as revisions_repo
from standardphysics_api.clearance import WIDTH_STEP_INCHES, width_codes, widths_png
from standardphysics_api.layout import plan_candidate

CASE_EAST = str(node_id("case_east"))
CASES = {str(node_id("case_west")), CASE_EAST}


def _sample(make_client):
    client = make_client(seed=True).__enter__()
    drain(client)
    return client, client.get("/api/scans").json()["scans"][0]["id"]


def _move(node: str, dx: float = 0.0) -> dict:
    return {"node_id": node, "delta_translation": {"x": dx, "y": 0.0, "z": 0.0}, "delta_rotation_z_degrees": 0.0}


def _post(client, scan_id: str, path: str, moves: list[dict], base_revision: int = 0):
    return client.post(f"/api/scans/{scan_id}/{path}", json={"base_revision": base_revision, "sequence": 7, "moves": moves})


def _widths(body: dict) -> np.ndarray:
    """The map's clear widths in inches, indexed like the grid: row 0 is the lowest y. Zero where nobody stands."""
    codes = np.array(Image.open(io.BytesIO(base64.b64decode(body["widths_png"]))))
    assert codes.shape == (body["rows"], body["columns"])
    return codes[::-1].astype(float) * body["width_step_inches"]


def _cell(body: dict, x: float, y: float) -> tuple[int, int]:
    size = body["cell_meters"]
    return int((y - body["origin"]["y"]) / size), int((x - body["origin"]["x"]) / size)


def _laid_out(client, scan_id: str, moves: list[dict]) -> tuple[SceneGraph, Scenario]:
    """The layout the server measures for these moves, built from the stored revision the way a check builds it."""
    with client.app.state.database.connect() as connection:
        base = revisions_repo.graph_of(revisions_repo.get_revision(connection, uuid.UUID(scan_id), 0))
        scenario = revisions_repo.get_scenario(connection, uuid.UUID(scan_id))
    candidate, _ = plan_candidate(base, [NodeMove.model_validate(move) for move in moves], construction=True)
    return candidate, scenario


def _route_widths(graph: SceneGraph, scenario: Scenario):
    """Every cell of every leg, with the width the leg measured there, in inches."""
    grid = build_grid(graph)
    clearance = clearance_map(grid)
    for start, goal in zip(scenario.stops, scenario.stops[1:], strict=False):
        leg = widest_path(
            grid, clearance, grid.to_cell(start.position.x, start.position.y),
            grid.to_cell(goal.position.x, goal.position.y), anchors=(start.anchor_node_id, goal.anchor_node_id),
        )
        assert leg.reachable and leg.pinch_cell in leg.path
        for row, col in leg.path:
            yield grid.to_world(row, col), to_inches(float(leg.clearance[row, col]) * 2)


def _route_findings(check: dict) -> dict[str, dict]:
    return {finding["id"]: finding for finding in check["findings"] if finding["check_id"] == "route_clear_width"}


def _assert_matches_the_check(client, scan_id: str, moves: list[dict]) -> dict:
    """The map agrees with the route widths measured on its layout, and its pinches with the check's findings."""
    body = _post(client, scan_id, "clearance-maps", moves).json()
    widths = _widths(body)
    for point, inches in _route_widths(*_laid_out(client, scan_id, moves)):
        stored = widths[_cell(body, point.x, point.y)]
        assert stored <= inches + COMPARISON_EPSILON < stored + WIDTH_STEP_INCHES
    check = _post(client, scan_id, "layout-checks", moves).json()
    assert body["graph_hash"] == check["graph_hash"]
    findings = _route_findings(check)
    assert {pinch["finding_id"] for pinch in body["pinches"]} == set(findings)
    for pinch in body["pinches"]:
        finding = findings[pinch["finding_id"]]
        assert pinch["inches"] == finding["measured_inches"]
        assert pinch["point"] == finding["locus"]["point"]
        assert pinch["meets_rule"] == (finding["outcome"] == "passes")
    return body


def _between_the_cases(body: dict) -> dict:
    return next(pinch for pinch in body["pinches"] if set(pinch["blocking_node_ids"]) == CASES)


def test_every_width_along_the_route_reads_the_same_on_the_map_as_in_the_check(make_client):
    client, scan_id = _sample(make_client)
    body = _assert_matches_the_check(client, scan_id, [])
    assert body["sequence"] == 7
    assert (body["cell_meters"], body["rotation_z_degrees"]) == (0.025, 0.0)
    assert body["bands"] == {"reduced_inches": 32.0, "route_inches": 36.0, "reduced_run_inches": 24.0,
                             "turning_inches": 60.0}
    pinch = _between_the_cases(body)
    assert (pinch["meets_rule"], pinch["origin"], pinch["destination"]) == (False, "Entrance", "Counter")
    assert pinch["inches"] == pytest.approx(31.0, abs=1e-6)


def test_an_unsaved_move_changes_the_map_and_the_map_still_matches_its_check(make_client):
    client, scan_id = _sample(make_client)
    scanned = _post(client, scan_id, "clearance-maps", []).json()
    into_the_aisle = [_move(CASE_EAST, dx=-0.3)]
    moved = _assert_matches_the_check(client, scan_id, into_the_aisle)
    assert moved["widths_png"] != scanned["widths_png"]
    assert moved["graph_hash"] != scanned["graph_hash"]
    assert _between_the_cases(moved)["inches"] == pytest.approx(_between_the_cases(scanned)["inches"] - to_inches(0.3))
    case = _laid_out(client, scan_id, [])[0].by_id(uuid.UUID(CASE_EAST))
    west_face, east_face = case.transform.position.x + np.array([-1, 1]) * case.dimensions.x / 2
    covered, uncovered = (west_face - 0.15, case.transform.position.y), (east_face - 0.15, case.transform.position.y)
    before, after = _widths(scanned), _widths(moved)
    assert before[_cell(scanned, *covered)] > 0 and after[_cell(moved, *covered)] == 0
    assert before[_cell(scanned, *uncovered)] == 0 and after[_cell(moved, *uncovered)] > 0


def test_putting_the_piece_back_gives_the_scanned_map(make_client):
    client, scan_id = _sample(make_client)
    scanned = _post(client, scan_id, "clearance-maps", []).json()
    _post(client, scan_id, "clearance-maps", [_move(CASE_EAST, dx=to_meters(5))])
    back = _post(client, scan_id, "clearance-maps", [_move(CASE_EAST)]).json()
    assert back["widths_png"] == scanned["widths_png"]
    assert back["pinches"] == scanned["pinches"]


def test_the_map_answers_strangers_and_signed_out_visitors_the_way_a_check_does(make_client, stranger):
    client, scan_id = _sample(make_client)
    with make_client(sign_in_as_owner=False) as anonymous:
        for visitor, status in ((stranger, 404), (anonymous, 401)):
            refused = _post(visitor, scan_id, "clearance-maps", [])
            assert refused.status_code == status
            assert refused.json() == _post(visitor, scan_id, "layout-checks", []).json()


def test_a_missing_revision_scan_or_piece_is_refused_like_a_check(make_client):
    client, scan_id = _sample(make_client)
    missing_revision = _post(client, scan_id, "clearance-maps", [], base_revision=3)
    assert (missing_revision.status_code, missing_revision.json()) == (404, {"error": "no such revision"})
    assert _post(client, str(uuid.uuid4()), "clearance-maps", []).status_code == 404
    unknown_piece = _post(client, scan_id, "clearance-maps", [_move("00000000-0000-0000-0000-000000000000")])
    assert unknown_piece.status_code == 400
    assert unknown_piece.json() == _post(client, scan_id, "layout-checks", [_move("00000000-0000-0000-0000-000000000000")]).json()


def test_without_a_confirmed_route_the_map_still_shows_the_floor_and_marks_no_gaps(make_client):
    client, scan_id = _sample(make_client)
    graph, _ = _laid_out(client, scan_id, [])
    measured = client.app.state.worker.stages.clearance(graph, None)
    assert measured.pinches == []
    assert (measured.metres > 0).any()


def test_widths_are_stored_rounded_down_in_half_inches_and_capped():
    inches = np.array([[0.0, 35.99, 36.0 - 1e-9, 36.0], [31.99, 32.0, 127.5, 400.0]])
    codes = width_codes(to_meters(inches) / 2)
    assert codes.tolist() == [[0, 71, 72, 72], [63, 64, 255, 255]]
    assert WIDTH_STEP_INCHES * 72 == 36.0


def test_the_first_row_of_the_picture_is_the_highest_y():
    metres = np.zeros((2, 3))
    metres[0, 0] = to_meters(10.0) / 2
    picture = np.array(Image.open(io.BytesIO(base64.b64decode(widths_png(metres)))))
    assert picture.tolist() == [[0, 0, 0], [20, 0, 0]]
