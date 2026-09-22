"""Original photo API, frozen by K for the photodriven review (supervisor 01:57 assignment).

Owner-authenticated frame listing and original frame bytes; no invented frame
identities, no downscaled copies, no EXIF display orientation silently applied.
Manual marks cut real deterministic crops through the same helper discovery
uses, and the mark's image_url names that crop.
"""

import io
import json

from PIL import Image

from conftest import create_scan, drain, put_artifact
from test_manual_marks import _mesh_bytes, _ready_scan, _stages, _room_payload


def _ready_without_frames(make_client):
    stages = _stages()
    client = make_client(stages=stages)
    scan_id = create_scan(client)
    put_artifact(client, scan_id, "room-json", _room_payload(), "room_json")
    put_artifact(client, scan_id, "room-usdz", b"usdz", "room_usdz")
    put_artifact(client, scan_id, "poses", b"{}", "poses")
    put_artifact(client, scan_id, "lidar-mesh", _mesh_bytes(), "lidar_mesh")
    client.post(f"/api/scans/{scan_id}/complete")
    drain(client)
    return client, scan_id


def _jpeg(width: int, height: int, color=(200, 180, 150)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_frames_lists_only_real_stored_frames_with_their_sensor_size(make_client):
    client, scan_id = _ready_without_frames(make_client)
    with client:
        put_artifact(client, scan_id, "frame-0000", _jpeg(64, 48), "frames")
        put_artifact(client, scan_id, "frame-0001", _jpeg(32, 24, color=(10, 20, 30)), "frames")

        listing = client.get(f"/api/scans/{scan_id}/frames")
        assert listing.status_code == 200, listing.text
        frames = listing.json()["frames"]
        assert len(frames) == 2
        assert frames[0]["frame_id"] == "frame-0000"
        assert frames[0]["width"] == 64
        assert frames[0]["height"] == 48
        assert frames[0]["image_url"] == f"/api/scans/{scan_id}/frames/frame-0000"
        assert frames[1]["frame_id"] == "frame-0001"
        assert frames[1]["width"] == 32
        assert frames[1]["height"] == 24

        stored = _jpeg(64, 48)
        fetched = client.get(f"/api/scans/{scan_id}/frames/frame-0000")
        assert fetched.status_code == 200
        assert fetched.headers["content-type"] == "image/jpeg"
        assert fetched.content == stored


def test_a_scan_with_no_frames_returns_an_empty_list_not_invented_ids(make_client):
    client, scan_id = _ready_without_frames(make_client)
    with client:
        listing = client.get(f"/api/scans/{scan_id}/frames")
        assert listing.status_code == 200
        assert listing.json() == {"frames": []}


def test_frame_routes_reject_non_frame_artifacts_and_bad_ids(make_client):
    client, scan_id = _ready_without_frames(make_client)
    with client:
        assert client.get(f"/api/scans/{scan_id}/frames/room-json").status_code == 400
        assert client.get(f"/api/scans/{scan_id}/frames/frame-9999").status_code == 404
        assert client.get(f"/api/scans/{scan_id}/frames/not-a-frame-id").status_code == 400


def test_stranger_cannot_read_frames_or_frame_bytes(make_client, stranger):
    client, scan_id = _ready_scan(make_client)
    with client:
        put_artifact(client, scan_id, "frame-0000", _jpeg(64, 48), "frames")
        with stranger as other:
            assert other.get(f"/api/scans/{scan_id}/frames").status_code == 404
            assert other.get(f"/api/scans/{scan_id}/frames/frame-0000").status_code == 404


def test_manual_mark_cuts_a_deterministic_crop_and_persists_image_url(make_client):
    client, scan_id = _ready_scan(make_client)
    with client:
        put_artifact(client, scan_id, "frame-0002", _jpeg(80, 60), "frames")
        mark = {
            "target_class": "outlet",
            "frame_id": "frame-0002",
            "sensor_box": [8, 8, 48, 40],
            "note": "power strip under the counter",
        }
        first = client.put(f"/api/scans/{scan_id}/revisions/0/observations", json=mark)
        assert first.status_code == 201, first.text
        saved = first.json()
        observation = saved["unlocalized_observations"][0]
        crop_url = observation["image_url"]
        assert crop_url
        crop = client.get(f"/api/scans/{scan_id}/crops/{crop_url}")
        assert crop.status_code == 200, crop.text
        assert crop.headers["content-type"] == "image/jpeg"
        assert crop.content

        second = client.put(f"/api/scans/{scan_id}/revisions/1/observations", json=mark)
        assert second.status_code == 201, second.text
        again = second.json()["unlocalized_observations"][1]
        assert again["image_url"] == crop_url


def test_manual_marks_demand_a_stored_frame_and_a_usable_box(make_client):
    client, scan_id = _ready_scan(make_client)
    with client:
        missing_frame = client.put(
            f"/api/scans/{scan_id}/revisions/0/observations",
            json={"target_class": "outlet", "frame_id": "frame-0404", "sensor_box": [0, 0, 10, 10]},
        )
        assert missing_frame.status_code == 400, missing_frame.text

        put_artifact(client, scan_id, "frame-0003", _jpeg(80, 60), "frames")
        degenerate = client.put(
            f"/api/scans/{scan_id}/revisions/0/observations",
            json={"target_class": "outlet", "frame_id": "frame-0003", "sensor_box": [40, 40, 8, 8]},
        )
        assert degenerate.status_code == 400, degenerate.text