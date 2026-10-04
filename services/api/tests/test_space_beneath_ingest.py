"""The space under each raised piece is measured at ingest, from the same read of the mesh as the floor."""

import hashlib
import json
import uuid

from standardphysics_contracts import to_meters
from standardphysics_fixtures.scanned_furniture import MeshSketch, ScannedTable
from standardphysics_pipeline.discovery import DiscoveryResult
from standardphysics_pipeline.floor_coverage import decode_cells
from standardphysics_pipeline.space_beneath import decode_centimetres

from conftest import create_scan, drain, no_blender_stages, put_artifact, usdz_fixture
from standardphysics_api import repository_revisions as revisions_repo

FLOOR_Y = -0.5
"""The floor's ARKit height; ingest lowers it to z = 0."""

TABLE = ScannedTable("Table", (0.0, 0.0), width=1.2, depth=0.8, height=0.75)


def _placed(y: float) -> list[float]:
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, y, 0, 1]


def _room_payload() -> bytes:
    def element(identifier, dimensions, y, **extra):
        return {"identifier": identifier, "dimensions": dimensions, "transform": _placed(y), "confidence": "high", **extra}

    return json.dumps({
        "version": 1,
        "story": "ground",
        "captureMetadata": {"source": "pilot"},
        "walls": [element("11111111-1111-1111-1111-111111111111", [4.0, 2.4, 0.2], FLOOR_Y)],
        "floors": [element("22222222-2222-2222-2222-222222222222", [4.0, 0.01, 4.0], FLOOR_Y)],
        "objects": [element(
            "44444444-4444-4444-4444-444444444444", [TABLE.width, TABLE.height, TABLE.depth],
            FLOOR_Y + TABLE.height / 2, category="table",
        )],
    }).encode()


def _mesh() -> bytes:
    """The floor and a table on legs, as the phone writes them: Y up, and the floor at `FLOOR_Y`."""
    sketch = TABLE.drawn(MeshSketch().floor((-2.0, -2.0, 2.0, 2.0)))
    room = sketch.vertices
    arkit = []
    for index in range(0, len(room), 3):
        x, y, z = room[index:index + 3]
        arkit += [x, z + FLOOR_Y, -y]
    return json.dumps({"parts": [{
        "id": "00000000-0000-0000-0000-000000000002",
        "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
        "vertices": arkit,
        "triangles": sketch.triangles,
    }]}).encode()


def _ingested(make_client, mesh: bytes | None):
    stages = no_blender_stages(label=lambda graph, **kwargs: graph, discover=lambda inputs: DiscoveryResult())
    client = make_client(stages=stages, evidence_settle_seconds=0.0).__enter__()
    scan_id = create_scan(client)
    if mesh is not None:
        put_artifact(client, scan_id, "lidar-mesh", mesh, "lidar_mesh")
    put_artifact(client, scan_id, "room-json", _room_payload(), "room_json")
    put_artifact(client, scan_id, "room-usdz", usdz_fixture(), "room_usdz")
    assert client.post(f"/api/scans/{scan_id}/complete").status_code == 200
    drain(client)
    with client.app.state.database.connect() as connection:
        return revisions_repo.graph_of(revisions_repo.get_revision(connection, uuid.UUID(scan_id), 0))


def _table(graph):
    return next(node for node in graph.nodes if node.raw_category == "table")


def test_ingest_records_the_floor_seen_under_a_table_and_how_high_it_stays_open(make_client):
    mesh = _mesh()
    graph = _ingested(make_client, mesh)
    beneath = _table(graph).space_beneath
    assert beneath is not None and beneath.mesh_sha256 == hashlib.sha256(mesh).hexdigest()
    seen = decode_cells(beneath.floor_seen, beneath.rows, beneath.columns)
    heights = decode_centimetres(beneath.open_cm, beneath.rows, beneath.columns)
    assert seen.mean() > 0.95
    assert to_meters(27.0) <= heights[beneath.rows // 2, beneath.columns // 2] <= TABLE.underside
    assert [coverage.mesh_sha256 for coverage in graph.floor_coverage] == [beneath.mesh_sha256]


def test_a_scan_without_a_mesh_records_no_space_beneath(make_client):
    assert _table(_ingested(make_client, None)).space_beneath is None
