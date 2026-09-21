"""Frozen allowlist tests (policy D01/D02/D03).

Adding a held-out or extra RGB path to the candidate input allowlist must fail
before file decoding; a changed digest must fail hash validation; train and
validation/test sets must be exactly disjoint by canonical source identity.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from standardphysics_pipeline.render_efficiency.allowlist import (
    AllowlistError,
    camera_from_transforms,
    load_allowlist,
    reject_heldout_entries,
)


def _allowlist_by_ids(frame_ids: list[str]) -> list[dict]:
    return [
        {
            "capture_id": "capture-1",
            "frame_id": fid,
            "file_path": f"images/{fid}.jpg",
            "rgb_sha256": "a" * 64,
        }
        for fid in frame_ids
    ]


def _manifest(train: list[str], validation: list[str], test: list[str]) -> dict:
    def entries(ids):
        return [
            {"capture_id": "capture-1", "frame_id": fid,
             "file_path": f"images/{fid}.jpg", "rgb_sha256": "a" * 64}
            for fid in ids
        ]

    return {"splits": {"train": entries(train), "validation": entries(validation), "test": entries(test)}}


def _write(tmp_path, name, obj):
    path = tmp_path / name
    path.write_text(json.dumps(obj))
    return path


def test_d01_heldout_validation_id_fails_before_decode(tmp_path):
    allowlist = _write(tmp_path, "allowlist.json", {"train": _allowlist_by_ids(["image-000038.jpg", "image-000149.jpg"])})
    manifest = _write(tmp_path, "manifest.json", _manifest(["image-000038.jpg", "image-000043.jpg"], ["image-000149.jpg"], []))
    entries = load_allowlist(allowlist)
    with pytest.raises(AllowlistError, match="held-out frame"):
        reject_heldout_entries(entries, manifest)


def test_d01_extra_id_fails_before_decode(tmp_path):
    allowlist = _write(tmp_path, "allowlist.json", {"train": _allowlist_by_ids(["image-000038.jpg", "image-000999.jpg"])})
    manifest = _write(tmp_path, "manifest.json", _manifest(["image-000038.jpg", "image-000043.jpg"], [], []))
    with pytest.raises(AllowlistError, match="not a manifest train ID"):
        reject_heldout_entries(load_allowlist(allowlist), manifest)


def test_d01_wrong_count_fails(tmp_path):
    allowlist = _write(tmp_path, "allowlist.json", {"train": _allowlist_by_ids(["image-000038.jpg"])})
    manifest = _write(tmp_path, "manifest.json", _manifest(["image-000038.jpg", "image-000043.jpg"], [], []))
    with pytest.raises(AllowlistError, match="frozen training split"):
        reject_heldout_entries(load_allowlist(allowlist), manifest)


def test_d02_duplicate_identity_fails(tmp_path):
    allowlist = _write(tmp_path, "allowlist.json", {"train": _allowlist_by_ids(["a.jpg", "a.jpg"])})
    with pytest.raises(AllowlistError, match="duplicate"):
        load_allowlist(allowlist)


def test_d02_missing_digest_fails(tmp_path):
    entries = _allowlist_by_ids(["a.jpg"])
    del entries[0]["rgb_sha256"]
    allowlist = _write(tmp_path, "allowlist.json", {"train": entries})
    with pytest.raises(AllowlistError, match="immutable identity"):
        load_allowlist(allowlist)


def test_d03_manifest_mixing_val_test_fails(tmp_path):
    allowlist = _write(tmp_path, "allowlist.json", {"train": _allowlist_by_ids(["a.jpg", "b.jpg"])})
    manifest = _write(tmp_path, "manifest.json", _manifest(["a.jpg", "b.jpg"], ["c.jpg"], ["c.jpg"]))
    with pytest.raises(AllowlistError, match="mixes validation and test"):
        reject_heldout_entries(load_allowlist(allowlist), manifest)


def test_d03_vs_test_disjoint_fails(tmp_path):
    allowlist = _write(tmp_path, "allowlist.json", {"train": _allowlist_by_ids(["a.jpg", "b.jpg"])})
    manifest = _write(tmp_path, "manifest.json", _manifest(["a.jpg", "b.jpg"], [], ["b.jpg"]))
    with pytest.raises(AllowlistError):
        reject_heldout_entries(load_allowlist(allowlist), manifest)


def test_clean_allowlist_passes_rejection(tmp_path):
    allowlist = _write(tmp_path, "allowlist.json", {"train": _allowlist_by_ids(["a.jpg", "b.jpg"])})
    manifest = _write(tmp_path, "manifest.json", _manifest(["a.jpg", "b.jpg"], ["c.jpg"], ["d.jpg"]))
    reject_heldout_entries(load_allowlist(allowlist), manifest)


def test_camera_from_transforms_uses_calibrated_intrinsics():
    frame = {
        "file_path": "images/x.jpg",
        "transform_matrix": np.eye(4).tolist(),
        "fl_x": 999.5, "fl_y": 888.5, "cx": 640.0, "cy": 480.0,
        "w": 1280, "h": 960,
    }
    camera = camera_from_transforms(frame)
    assert camera.width == 1280 and camera.height == 960
    assert camera.fx == pytest.approx(999.5)
    assert camera.fy == pytest.approx(888.5)


def test_camera_from_transforms_rejects_bad_matrix():
    bad = {
        "file_path": "images/x.jpg",
        "transform_matrix": [[np.nan, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
        "fl_x": 1.0, "fl_y": 1.0, "cx": 0.0, "cy": 0.0, "w": 100, "h": 100,
    }
    with pytest.raises(AllowlistError):
        camera_from_transforms(bad)
