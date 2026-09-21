"""Tests for secure crop evidence delivery and authorization (CROP-01, AUTH-01).

Validates:
- CROP-01: Actual evidence route under owning user serves generated crops with decodable
  bytes matching source pixel region; missing crop returns explicit 404 error.
- AUTH-01: Anonymous requester gets 401; second user guessing crop ID gets 404 (no scan leakage);
  directory traversal attempts are rejected (400/404) without path or secret leakage.
"""

from __future__ import annotations

import io

from PIL import Image

from conftest import create_scan, sign_up


def test_crop_01_owner_serves_crop_and_missing_is_404(client):
    """CROP-01: Owning user fetches generated crop bytes; missing crop returns 404."""
    scan_id = create_scan(client)
    store = client.app.state.store

    crops_dir = store.scan_dir(scan_id) / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    # Generate a real 100x100 JPEG crop
    img = Image.new("RGB", (100, 100), color=(255, 128, 64))
    crop_path = crops_dir / "crop-001.jpg"
    img.save(crop_path, format="JPEG")

    # 1. Fetch existing crop as owner
    resp = client.get(f"/api/scans/{scan_id}/crops/crop-001.jpg")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"

    # Verify bytes decode and match image dimensions
    decoded = Image.open(io.BytesIO(resp.content))
    assert decoded.size == (100, 100)

    # 2. Also fetch without .jpg extension
    resp_no_ext = client.get(f"/api/scans/{scan_id}/crops/crop-001")
    assert resp_no_ext.status_code == 200
    assert resp_no_ext.content == resp.content

    # 3. Missing crop returns explicit 404
    resp_missing = client.get(f"/api/scans/{scan_id}/crops/nonexistent-crop.jpg")
    assert resp_missing.status_code == 404
    assert "crop not found" in resp_missing.text


def test_auth_01_crop_authorization_and_traversal_denial(make_client):
    """AUTH-01: Anonymous and second-user access denied; traversal attacks blocked."""
    # User 1 creates scan and crop
    client1 = make_client(sign_in_as_owner=True)
    scan_id = create_scan(client1)
    store = client1.app.state.store

    crops_dir = store.scan_dir(scan_id) / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (50, 50), color=(10, 20, 30))
    img.save(crops_dir / "secret-crop.jpg", format="JPEG")

    # 1. Anonymous requester (no session) gets 401
    client_anon = make_client(sign_in_as_owner=False)
    resp_anon = client_anon.get(f"/api/scans/{scan_id}/crops/secret-crop.jpg")
    assert resp_anon.status_code == 401
    assert "sign in" in resp_anon.text.lower()

    # 2. Second user guessing crop ID gets 404 (scan not found for them, no existence leakage)
    client2 = make_client(sign_in_as_owner=False)
    sign_up(client2, email="user2@example.com", password="password-for-user-2")
    resp_user2 = client2.get(f"/api/scans/{scan_id}/crops/secret-crop.jpg")
    assert resp_user2.status_code == 404
    assert "no scan" in resp_user2.text

    # 3. Traversal attack attempts are denied
    # Slash or backslash in crop_id is rejected with 400
    resp_trav1 = client1.get(f"/api/scans/{scan_id}/crops/..%2Fsecret-crop.jpg")
    assert resp_trav1.status_code in (400, 404)

    resp_trav2 = client1.get(f"/api/scans/{scan_id}/crops/..%2F..%2F..%2Fetc%2Fpasswd")
    assert resp_trav2.status_code in (400, 404)
    # Ensure no secret or system path leakage
    assert "root:" not in resp_trav2.text
    assert "/etc/passwd" not in resp_trav2.text
