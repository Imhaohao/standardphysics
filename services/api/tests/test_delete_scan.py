"""Deleting a scan removes its rows and its files."""
import hashlib
import uuid

from conftest import REPO, create_scan, drain, put_artifact


def test_delete_removes_the_scan(client):
    scan_id = create_scan(client)
    client.put(
        f"/api/scans/{scan_id}/artifacts/room.json",
        content=b"{}",
        headers={"X-Artifact-Kind": "room_json", "X-Checksum-SHA256": hashlib.sha256(b"{}").hexdigest()},
    )
    assert client.get(f"/api/scans/{scan_id}").status_code == 200
    assert client.delete(f"/api/scans/{scan_id}").status_code == 204
    assert client.get(f"/api/scans/{scan_id}").status_code == 404
    assert scan_id not in [s["id"] for s in client.get("/api/scans").json()["scans"]]


def test_deleting_twice_is_not_found(client):
    scan_id = create_scan(client)
    assert client.delete(f"/api/scans/{scan_id}").status_code == 204
    assert client.delete(f"/api/scans/{scan_id}").status_code == 404


def test_deleting_a_scan_that_never_existed(client):
    assert client.delete(f"/api/scans/{uuid.uuid4()}").status_code == 404


def test_a_processed_scan_can_be_deleted(client):
    """Processing leaves job attempts behind, and they must not hold the scan in place."""
    phone = REPO / "datasets/phone/test1"
    scan_id = create_scan(client)
    put_artifact(client, scan_id, "room-json", (phone / "room.json").read_bytes(), "room_json")
    put_artifact(client, scan_id, "room-usdz", (phone / "room.usdz").read_bytes(), "room_usdz")
    client.post(f"/api/scans/{scan_id}/complete")
    drain(client)

    assert client.delete(f"/api/scans/{scan_id}").status_code == 204
    assert client.get(f"/api/scans/{scan_id}").status_code == 404
