"""A real RoomPlan export and the sample shop, through every stage."""

import json

from conftest import FIXTURE_DATA, create_scan, drain, put_artifact

REAL = FIXTURE_DATA / "real"


def _upload_real_room(client, room: str) -> str:
    scan_id = create_scan(client)
    put_artifact(client, scan_id, "room-json", (REAL / f"{room}.room.json").read_bytes(), "room_json")
    put_artifact(client, scan_id, "room-usdz", (REAL / f"{room}.usdz").read_bytes(), "room_usdz")
    put_artifact(client, scan_id, "room-metadata", (REAL / f"{room}.metadata.plist").read_bytes(), "room_metadata")
    client.post(f"/api/scans/{scan_id}/complete")
    drain(client)
    return scan_id


def test_a_real_export_becomes_a_ready_scan_with_a_scene(client):
    scan_id = _upload_real_room(client, "apple_livingroom")
    assert client.get(f"/api/scans/{scan_id}").json()["state"] == "ready"
    scene = client.get(f"/api/scans/{scan_id}/scene").json()
    room = json.loads((REAL / "apple_livingroom.room.json").read_text())
    expected = sum(len(room.get(key) or []) for key in ("walls", "doors", "windows", "openings", "floors", "objects"))
    assert len(scene["nodes"]) == expected
    assert scene["scan_id"] == scan_id


def test_display_geometry_falls_back_to_the_graph_when_conversion_fails(client):
    scan_id = _upload_real_room(client, "apple_bedroom3")
    response = client.get(f"/api/scans/{scan_id}/scene.glb")
    assert response.status_code == 200
    assert response.content[:4] == b"glTF"


def test_a_real_scan_without_stops_has_no_assessment_yet(client):
    scan_id = _upload_real_room(client, "apple_bedroom3")
    assert client.get(f"/api/scans/{scan_id}/assessment").status_code == 404


def test_the_sample_shop_is_ready_with_its_findings(make_client):
    with make_client(seed=True) as client:
        drain(client)
        scans = client.get("/api/scans").json()["scans"]
        assert [s["name"] for s in scans] == ["Sample boba shop"]
        scan_id = scans[0]["id"]
        assert scans[0]["state"] == "ready"
        assessment = client.get(f"/api/scans/{scan_id}/assessment").json()
        widths = {round(f["measured_inches"]) for f in assessment["findings"] if f["outcome"] == "problem" and f["measured_inches"]}
        assert 31 in widths
        assert client.get(f"/api/scans/{scan_id}/scenario").json()["stops"][0]["name"] == "Entrance"
        assert client.get(f"/api/scans/{scan_id}/scene.glb").content[:4] == b"glTF"


def test_findings_with_a_locus_get_a_render(make_client):
    with make_client(seed=True) as client:
        drain(client)
        scan_id = client.get("/api/scans").json()["scans"][0]["id"]
        finding = next(f for f in client.get(f"/api/scans/{scan_id}/assessment").json()["findings"] if f["locus"])
        render_url = finding["locus"]["render_url"]
        assert render_url == f"/api/scans/{scan_id}/renders/{finding['id']}.png"
        assert client.get(render_url).content.startswith(b"\x89PNG")


def test_seeding_twice_keeps_one_sample_shop(make_client):
    with make_client(seed=True) as client:
        drain(client)
    with make_client(seed=True) as client:
        assert len(client.get("/api/scans").json()["scans"]) == 1


def test_without_verified_rules_the_sample_shop_reports_nothing(make_client):
    from conftest import no_blender_stages
    from standardphysics_agents import VerificationLedger

    with make_client(seed=True, stages=no_blender_stages(ledger_factory=VerificationLedger)) as client:
        drain(client)
        scan_id = client.get("/api/scans").json()["scans"][0]["id"]
        assert client.get(f"/api/scans/{scan_id}/assessment").json()["findings"] == []


def test_an_assessment_says_how_many_rules_ran(make_client):
    from conftest import no_blender_stages
    from standardphysics_agents import VerificationLedger

    with make_client(seed=True, stages=no_blender_stages(ledger_factory=VerificationLedger)) as client:
        drain(client)
        scan_id = client.get("/api/scans").json()["scans"][0]["id"]
        assert client.get(f"/api/scans/{scan_id}/assessment").json()["rules_checked"] == 0
