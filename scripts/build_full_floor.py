"""Turn a placed set of walks into one scan carrying all of their measurements.

`merge_captures.py` puts several walks of one floor into a single scan as boxes
and leaves them where they were captured. Somebody then drags each walk into
place in the workspace and saves, because the geometry cannot say how they fit:
a floor of parallel shelf rows correlates with itself at many angles.

This takes that saved placement and applies it to everything the boxes stood
for. Each walk's LiDAR mesh and camera poses are moved by the same in-plane
motion the owner gave its boxes, so the photographs keep pointing at the
surfaces they photographed, and the result is one scan a texture bake can read.

The motion is recovered rather than trusted: every node's placed position is a
correspondence against where it started, and those go through the registration
fit, which refuses when they do not agree on one rigid motion. A walk nobody
moved comes through as the identity it is.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import uuid

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "services" / "api"))

from standardphysics_contracts import CreateScanRequest, SceneGraph  # noqa: E402
from standardphysics_pipeline.registration import align_points  # noqa: E402

from standardphysics_api import repository  # noqa: E402
from standardphysics_api.db import Database  # noqa: E402

PLACEMENT_TOLERANCE_M = 0.05
"""How far a placed box may sit from the motion fitted to all of them.

A drag moves every box of a walk by exactly one motion, so the residual here is
arithmetic, not measurement. The tolerance only has to absorb rounding.
"""


def _graph(connection, scan_id: uuid.UUID, revision: int | None) -> SceneGraph:
    row = repository.get_revision(connection, scan_id, revision)
    if row is None:
        raise SystemExit(f"no revision {revision} on {scan_id}")
    return repository.graph_of(row)


def _placement_of(before: SceneGraph, after: SceneGraph, node_ids: list[str]):
    """The motion the owner gave one walk, read back off its boxes."""
    start = {str(node.id): node for node in before.nodes}
    end = {str(node.id): node for node in after.nodes}
    pairs = [(start[i], end[i]) for i in node_ids if i in start and i in end]
    if len(pairs) < 3:
        raise SystemExit("a walk needs at least three boxes to read its placement from")
    source = [(a.transform.m[3], a.transform.m[7]) for a, _ in pairs]
    target = [(b.transform.m[3], b.transform.m[7]) for _, b in pairs]
    return align_points(source, target, tolerance=PLACEMENT_TOLERANCE_M)


def _moved_mesh(mesh: dict, alignment) -> dict:
    """Every LiDAR part turned and slid with the boxes it was measured beside."""
    cos, sin = np.cos(alignment.yaw), np.sin(alignment.yaw)
    tx, ty = alignment.translation
    for part in mesh.get("parts", []):
        m = list(part["transform"])
        x, y = m[12], m[13]
        m[12], m[13] = cos * x - sin * y + tx, sin * x + cos * y + ty
        r00, r01, r10, r11 = m[0], m[1], m[4], m[5]
        m[0], m[1] = cos * r00 - sin * r10, cos * r01 - sin * r11
        m[4], m[5] = sin * r00 + cos * r10, sin * r01 + cos * r11
        part["transform"] = m
    return mesh


def _moved_poses(poses: list[dict] | dict, alignment):
    """Every camera turned and slid, so it still looks where it looked."""
    records = poses if isinstance(poses, list) else poses.get("poses", [])
    cos, sin = np.cos(alignment.yaw), np.sin(alignment.yaw)
    tx, ty = alignment.translation
    for record in records:
        m = list(record["transform"])
        x, y = m[12], m[13]
        m[12], m[13] = cos * x - sin * y + tx, sin * x + cos * y + ty
        r00, r01, r10, r11 = m[0], m[1], m[4], m[5]
        m[0], m[1] = cos * r00 - sin * r10, cos * r01 - sin * r11
        m[4], m[5] = sin * r00 + cos * r10, sin * r01 + cos * r11
        record["transform"] = m
    return poses


def _carry_frames(source: pathlib.Path, destination: pathlib.Path, prefix: str) -> int:
    """Photographs copied under a name that says which walk took them."""
    frames = sorted(source.glob("frame-*"))
    for frame in frames:
        shutil.copy2(frame, destination / f"{prefix}-{frame.name}")
    return len(frames)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--placed-scan", required=True, help="the merged scan whose walks were placed")
    parser.add_argument("--captures", required=True, type=pathlib.Path, help="directory of capture folders")
    parser.add_argument("--name", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--db", type=pathlib.Path, default=pathlib.Path("services/api/var/standardphysics.sqlite3"))
    parser.add_argument("--scans", type=pathlib.Path, default=pathlib.Path("services/api/var/scans"))
    args = parser.parse_args()

    placed_id = uuid.UUID(args.placed_scan)
    manifest = json.loads((args.scans / str(placed_id) / "rooms.json").read_text())

    database = Database(args.db)
    with database.connect() as connection:
        before = _graph(connection, placed_id, 0)
        after = _graph(connection, placed_id, None)
    if after.revision == 0:
        raise SystemExit("that scan's walks have not been placed yet: align them and save first")

    by_name = {directory.name: directory for directory in args.captures.iterdir() if directory.is_dir()}
    scan_id = uuid.uuid4()
    out = args.scans / str(scan_id) / "artifacts"
    out.mkdir(parents=True, exist_ok=True)

    parts, poses, frames = [], [], 0
    for room in manifest["rooms"]:
        alignment = _placement_of(before, after, room["node_ids"])
        directory = next((d for d in by_name.values() if _capture_name(d) == room["name"]), None)
        if directory is None:
            raise SystemExit(f"no capture folder for the walk called {room['name']}")
        mesh = _moved_mesh(json.loads((directory / "lidar-mesh.json").read_text()), alignment)
        parts.extend(mesh.get("parts", []))
        walk = _moved_poses(json.loads((directory / "poses.json").read_text()), alignment)
        records = walk if isinstance(walk, list) else walk.get("poses", [])
        prefix = room["name"].replace(" ", "-")
        for record in records:
            record["frame_id"] = f"{prefix}-{record['frame_id']}"
        poses.extend(records)
        frames += _carry_frames(directory / "frames", out, prefix)
        print(f"  {room['name']:12} turned {np.degrees(alignment.yaw):7.2f}°, "
              f"residual {alignment.residual_max * 1000:.1f} mm")

    (out / "lidar-mesh").write_text(json.dumps({"parts": parts}))
    (out / "poses").write_text(json.dumps(poses))
    (out / "room-json").write_text(after.model_dump_json())

    with database.transaction() as connection:
        repository.insert_scan(
            connection,
            CreateScanRequest(name=args.name, device_model="merged floor", duration_seconds=0),
            uuid.UUID(args.owner),
            scan_id=scan_id,
            state="ready",
        )
        repository.save_revision(connection, after.model_copy(update={"scan_id": scan_id, "revision": 0}), source="owner")

    print(f"\n{args.name}: {scan_id}")
    print(f"  {len(parts)} mesh parts, {len(poses)} cameras, {frames} photographs")
    return 0


def _capture_name(directory: pathlib.Path) -> str:
    capture = directory / "capture.json"
    if capture.is_file():
        name = json.loads(capture.read_text()).get("name")
        if name:
            return str(name)
    return directory.name[:8]


if __name__ == "__main__":
    raise SystemExit(main())
