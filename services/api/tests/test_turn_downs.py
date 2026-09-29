"""Turning down where a suggestion put a piece keeps it out of that spot from then on, and is kept as a record."""

import json
import math

from conftest import drain
from standardphysics_api.turn_downs import REJECTED_SPOT_INCHES


def _sample(make_client):
    client = make_client(seed=True).__enter__()
    drain(client)
    return client, client.get("/api/scans").json()["scans"][0]["id"]


def _chair(client, scan_id):
    scene = client.get(f"/api/scans/{scan_id}/scene").json()
    return next(node for node in scene["nodes"] if node["label"].lower().startswith("chair") and node["movable"])


def _move(node_id, dx):
    return {"node_id": node_id, "delta_translation": {"x": dx, "y": 0.0, "z": 0.0}, "delta_rotation_z_degrees": 0.0}


def _turn_down(client, scan_id, moves, suggestion=()):
    body = {"base_revision": 0, "turned_down": moves, "suggestion": list(suggestion), "model": "Kimi K3"}
    return client.post(f"/api/scans/{scan_id}/turn-downs", json=body)


def test_a_turned_down_piece_is_saved_as_a_spot_to_keep_it_out_of(make_client):
    client, scan_id = _sample(make_client)
    chair = _chair(client, scan_id)
    moved = _move(chair["id"], 0.6)
    response = _turn_down(client, scan_id, [moved], suggestion=[moved])
    assert response.status_code == 200
    [wish] = [wish for wish in response.json()["owner_wishes"] if wish["kind"] == "not_there"]
    here = chair["transform"]["m"]
    assert wish["node_id"] == chair["id"] and wish["inches"] == REJECTED_SPOT_INCHES
    assert math.isclose(wish["at"]["x"], here[3] + 0.6, abs_tol=1e-6) and math.isclose(wish["at"]["y"], here[7])
    assert wish["text"] == "Keep the chair out of the spot you turned down"


def test_turning_down_the_same_spot_twice_saves_it_once_and_records_both(make_client):
    client, scan_id = _sample(make_client)
    chair = _chair(client, scan_id)
    _turn_down(client, scan_id, [_move(chair["id"], 0.6)])
    wishes = _turn_down(client, scan_id, [_move(chair["id"], 0.65)]).json()["owner_wishes"]
    assert [wish["kind"] for wish in wishes].count("not_there") == 1
    with client.app.state.database.connect() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM rearrangement_teacher_events WHERE scan_id=? AND kind='placement_turned_down'",
            (scan_id,),
        ).fetchall()
    assert len(rows) == 2
    record = json.loads(rows[0]["payload_json"])
    assert record["model"] == "Kimi K3" and record["turned_down"][0]["node_id"] == chair["id"] and record["graph_hash"]


def test_a_piece_that_is_not_in_the_shop_is_refused(make_client):
    client, scan_id = _sample(make_client)
    response = _turn_down(client, scan_id, [_move("00000000-0000-0000-0000-000000000009", 0.5)])
    assert response.status_code == 400
