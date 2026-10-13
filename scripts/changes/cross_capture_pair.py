"""Build a before and after pair from two real captures that walked through the same space at different times.

The Moffett A-102 floor was scanned as four captures, minutes apart, and stitched into one
floor plan. Each capture's furniture shares node ids with the floor plan, so a rigid fit of
the shared nodes places its ARKit camera track on the floor. Photos from either walk whose
view lands two metres ahead in the same half-metre cell look at the same place; those become
before.mp4 and after.mp4, one photo per frame and turned upright, and truth.json records each
frame's camera position on the floor. Nothing was staged, so the truth lists no changes:
whatever people moved between the walks is real, and everything else reported is a false alarm.

    python scripts/changes/cross_capture_pair.py --before left --after top --out /tmp/library-pair

Run it from a checkout that holds datasets/phone/moffett and services/api/var.
"""

import argparse
import json
import pathlib
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from bake_library_textures import DATA_DIR, ROOMS, latest_graph, room_capture  # noqa: E402
from standardphysics_pipeline.textures.camera import load_cameras  # noqa: E402

from standardphysics_api.db import Database  # noqa: E402

CELL_M = 0.5
LOOK_AHEAD_M = 2.0
FPS = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", choices=tuple(ROOMS), required=True)
    parser.add_argument("--after", choices=tuple(ROOMS), required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    return parser.parse_args()


def centres(nodes) -> dict[str, np.ndarray]:
    return {str(node.id): np.asarray(node.transform.m, dtype=float).reshape(4, 4)[:3, 3] for node in nodes}


def rigid_fit(source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The rotation and translation that best carry `source` points onto `target` (Kabsch)."""
    source_mean, target_mean = source.mean(axis=0), target.mean(axis=0)
    u, _, vt = np.linalg.svd((source - source_mean).T @ (target - target_mean))
    flip = np.diag([1.0, 1.0, np.sign(np.linalg.det(vt.T @ u.T))])
    rotation = vt.T @ flip @ u.T
    return rotation, target_mean - rotation @ source_mean


def walk_on_floor(name: str, floor_centres: dict[str, np.ndarray]) -> dict:
    """One capture's photos with their camera positions and look-at cells in floor coordinates."""
    capture = room_capture(name, *ROOMS[name], np.eye(4))
    room_centres = centres(capture.graph.nodes)
    shared = sorted(set(room_centres) & set(floor_centres))
    rotation, offset = rigid_fit(np.array([room_centres[k] for k in shared]), np.array([floor_centres[k] for k in shared]))
    cameras = load_cameras(capture.poses_path, capture.frame_paths, capture.capture_to_room)
    positions = np.array([camera.position for camera in cameras]) @ rotation.T + offset
    ahead = positions + LOOK_AHEAD_M * (np.array([camera.forward for camera in cameras]) @ rotation.T)
    return {
        "frames": [capture.frame_paths[camera.frame_id] for camera in cameras],
        "positions": positions,
        "cells": [tuple(cell) for cell in np.floor(ahead[:, :2] / CELL_M).astype(int)],
    }


def write_video(frames: list[pathlib.Path], target: pathlib.Path) -> None:
    listing = target.with_suffix(".txt")
    listing.write_text("".join(f"file '{frame.resolve()}'\nduration {1 / FPS}\n" for frame in frames))
    command = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
               "-vf", f"transpose=1,scale=-2:960,fps={FPS}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target)]
    subprocess.run(command, check=True)
    listing.unlink()


def camera_pose(position: np.ndarray) -> list:
    pose = np.eye(4)
    pose[:3, 3] = position
    return pose.round(5).tolist()


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    floor_centres = centres(latest_graph(Database(DATA_DIR / "standardphysics.sqlite3")).nodes)
    walks = {"before": walk_on_floor(args.before, floor_centres), "after": walk_on_floor(args.after, floor_centres)}
    overlap = set(walks["before"]["cells"]) & set(walks["after"]["cells"])
    cameras, heights = {}, {}
    for role, walk in walks.items():
        keep = [index for index, cell in enumerate(walk["cells"]) if cell in overlap]
        write_video([walk["frames"][index] for index in keep], args.out / f"{role}.mp4")
        cameras[role] = [camera_pose(walk["positions"][index]) for index in keep]
        heights[role] = round(float(np.median(walk["positions"][keep, 2])), 3)
    truth = {
        "frame": "Moffett A-102 floor plan, metres, z up; camera positions from ARKit through each capture's fitted floor transform",
        "source": {"before": args.before, "after": args.after},
        "shared_cells": len(overlap),
        "phone_height_m": heights,
        "cameras_opencv_c2w": cameras,
        "changes": [],
        "unverifiable": [],
    }
    (args.out / "truth.json").write_text(json.dumps(truth, indent=1))
    print(json.dumps({"shared_cells": len(overlap), "frames": {role: len(poses) for role, poses in cameras.items()}, "phone_height_m": heights}))


if __name__ == "__main__":
    main()
