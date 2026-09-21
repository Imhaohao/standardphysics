"""Frozen photographic input allowlist for benchmark surface builds.

The candidate builder may only open training RGBs whose complete immutable
identity (capture ID + frame ID + source RGB SHA-256) is recorded in the
allowlist.  Held-out, extra, duplicate or byte-changed inputs are rejected
before any image is decoded.  Validation lives here so both the CLI and the
tests enforce the identical gate (policy D01-D03, P01).
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

from ..textures.camera import PhotoCamera

CAMERA_FLIP = np.diag([1.0, -1.0, -1.0, 1.0])

REQUIRED_IDENTITY_FIELDS = ("capture_id", "frame_id", "file_path", "rgb_sha256")


class AllowlistError(ValueError):
    """A photographic input that must not be decoded."""


def load_allowlist(path: pathlib.Path) -> list[dict]:
    """Read the mandatory frozen input allowlist and validate its shape.

    Each entry carries the full immutable source identity; duplicates or
    entries without a digest are rejected before any image is opened.
    """
    raw = json.loads(pathlib.Path(path).read_text())
    entries = raw["train"] if isinstance(raw, dict) and "train" in raw else raw
    if not isinstance(entries, list) or not entries:
        raise AllowlistError("allowlist must be a non-empty train entry list")
    seen: set[str] = set()
    normalized = []
    for entry in entries:
        missing = [key for key in REQUIRED_IDENTITY_FIELDS if key not in entry]
        if missing:
            raise AllowlistError(f"allowlist entry lacks immutable identity fields: {missing}")
        key = entry["frame_id"]
        if key in seen:
            raise AllowlistError(f"duplicate allowlist entry: {key}")
        seen.add(key)
        normalized.append(dict(entry))
    return normalized


def reject_heldout_entries(entries: list[dict], manifest_path: pathlib.Path) -> None:
    """Any allowlist frame ID outside the manifest train split fails, before decoding.

    Validation and test sets stay exactly disjoint from the allowlist by
    canonical frame identity (D01/D03); the count must equal the frozen split.
    """
    manifest = json.loads(pathlib.Path(manifest_path).read_text())
    splits = manifest.get("splits", manifest)
    train_ids = {entry["frame_id"] for entry in splits.get("train", [])}
    validation_ids = {entry["frame_id"] for entry in splits.get("validation", [])}
    test_ids = {entry["frame_id"] for entry in splits.get("test", [])}
    if validation_ids & test_ids:
        raise AllowlistError("manifest itself mixes validation and test identities")
    if not train_ids:
        raise AllowlistError("manifest carries no train identities")
    for entry in entries:
        fid = entry["frame_id"]
        if fid in validation_ids or fid in test_ids:
            raise AllowlistError(f"held-out frame {fid} in training allowlist; rejected before decoding")
        if fid not in train_ids:
            raise AllowlistError(f"frame {fid} is not a manifest train ID; rejected before decoding")
    if len(entries) != len(train_ids):
        raise AllowlistError(
            f"allowlist covers {len(entries)} frames but the frozen training split has {len(train_ids)}"
        )


def camera_from_transforms(frame: dict) -> PhotoCamera:
    """Calibrated camera from a prepared-dataset frame (c2w + per-frame intrinsics)."""
    c2w = np.asarray(frame["transform_matrix"], dtype=np.float64).reshape(4, 4)
    if not np.isfinite(c2w).all() or not np.allclose(c2w[3], [0, 0, 0, 1], atol=1e-5):
        raise AllowlistError(f"invalid transform matrix for {frame.get('file_path')}")
    room_to_camera = CAMERA_FLIP @ np.linalg.inv(c2w)
    return PhotoCamera(
        frame_id=frame.get("frame_id", pathlib.Path(frame["file_path"]).stem),
        room_to_camera=room_to_camera.astype(np.float64),
        fx=float(frame["fl_x"]),
        fy=float(frame["fl_y"]),
        cx=float(frame["cx"]),
        cy=float(frame["cy"]),
        width=int(frame["w"]),
        height=int(frame["h"]),
        timestamp=0.0,
    ).resized(int(frame["w"]), int(frame["h"]))


__all__ = [
    "AllowlistError",
    "REQUIRED_IDENTITY_FIELDS",
    "camera_from_transforms",
    "load_allowlist",
    "reject_heldout_entries",
]
