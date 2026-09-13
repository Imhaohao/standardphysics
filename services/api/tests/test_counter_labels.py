"""The owner marks which object is the counter, so the counter checks have something to measure."""

from conftest import REPO, create_scan, drain, put_artifact

PHONE = REPO / "datasets/phone"


def _phone_scan(client, name: str) -> str:
    scan_id = create_scan(client)
    put_artifact(client, scan_id, "room-json", (PHONE / name / "room.json").read_bytes(), "room_json")
    put_artifact(client, scan_id, "room-usdz", (PHONE / name / "room.usdz").read_bytes(), "room_usdz")
    client.post(f"/api/scans/{scan_id}/complete")
    drain(client)
    return scan_id


def _first(scene: dict, kind: str) -> dict:
    return next(node for node in scene["nodes"] if node["kind"] == kind)


def _counter_path(scan_id: str, revision: int, node_id: str) -> str:
    return f"/api/scans/{scan_id}/revisions/{revision}/counters/{node_id}"


def test_marking_an_object_as_the_counter_checks_it(client):
    scan_id = _phone_scan(client, "ravida")
    before = client.get(f"/api/scans/{scan_id}/assessment").json()
    assert "service_counter_height" not in {finding["check_id"] for finding in before["findings"]}
    target = _first(client.get(f"/api/scans/{scan_id}/scene").json(), "object")

    response = client.put(_counter_path(scan_id, 0, target["id"]))
    assert response.status_code == 201
    marked = next(node for node in response.json()["nodes"] if node["id"] == target["id"])
    assert (marked["label"], marked["labeled_by"], marked["movable"]) == ("service counter", "owner", False)
    assert response.json()["revision"] == 1

    drain(client)
    after = client.get(f"/api/scans/{scan_id}/assessment").json()
    assert after["graph_revision"] == 1
    assert "service_counter_height" in {finding["check_id"] for finding in after["findings"]}


def test_unmarking_restores_the_scanned_category(client):
    scan_id = _phone_scan(client, "ravida")
    target = _first(client.get(f"/api/scans/{scan_id}/scene").json(), "object")
    client.put(_counter_path(scan_id, 0, target["id"]))
    drain(client)
    response = client.delete(_counter_path(scan_id, 1, target["id"]))
    assert response.status_code == 201
    restored = next(node for node in response.json()["nodes"] if node["id"] == target["id"])
    assert restored["label"] == target["raw_category"]


def test_only_an_object_can_be_the_counter(client):
    scan_id = _phone_scan(client, "ravida")
    wall = _first(client.get(f"/api/scans/{scan_id}/scene").json(), "wall")
    assert client.put(_counter_path(scan_id, 0, wall["id"])).status_code == 400


def test_marking_from_an_old_revision_is_refused(client):
    scan_id = _phone_scan(client, "ravida")
    target = _first(client.get(f"/api/scans/{scan_id}/scene").json(), "object")
    assert client.put(_counter_path(scan_id, 0, target["id"])).status_code == 201
    assert client.put(_counter_path(scan_id, 0, target["id"])).status_code == 409
