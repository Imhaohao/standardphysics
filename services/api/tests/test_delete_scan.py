"""Deleting a scan removes its rows and its files."""
import pathlib, uuid
from fastapi.testclient import TestClient
from standardphysics_api.app import create_app
from standardphysics_api.settings import Settings


def client(tmp):
    app = create_app(Settings(data_dir=pathlib.Path(tmp)), run_worker=False)
    return TestClient(app)


def test_delete_removes_the_scan(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/scans", json={"name": "Doomed", "device_model": "x", "duration_seconds": 1.0}).json()
    scan_id = created["id"]
    c.put(f"/api/scans/{scan_id}/artifacts/room.json",
          content=b"{}", headers={"X-Artifact-Kind": "room_json", "X-Checksum-SHA256": __import__("hashlib").sha256(b"{}").hexdigest()})
    assert c.get(f"/api/scans/{scan_id}").status_code == 200
    assert c.delete(f"/api/scans/{scan_id}").status_code == 204
    assert c.get(f"/api/scans/{scan_id}").status_code == 404
    assert scan_id not in [s["id"] for s in c.get("/api/scans").json()["scans"]]


def test_deleting_twice_is_not_found(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/scans", json={"name": "Doomed", "device_model": "x", "duration_seconds": 1.0}).json()
    c.delete(f"/api/scans/{created['id']}")
    assert c.delete(f"/api/scans/{created['id']}").status_code == 404


def test_deleting_a_scan_that_never_existed(tmp_path):
    assert client(tmp_path).delete(f"/api/scans/{uuid.uuid4()}").status_code == 404
