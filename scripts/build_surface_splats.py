"""Deterministic surface-Gaussian build for one preserved Moffett capture.

Centres stay on the measured LiDAR surface and colours come from best-view photo
sampling (``textures.scan_colour``), so this is source-supported display geometry
rather than a learned reconstruction.  It fails clearly on missing cameras,
empty support or non-finite data and never publishes or overwrites originals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from moffett_image_registration import CAPTURES
from PIL import Image
from standardphysics_pipeline.ingest import capture_to_room_from_payload
from standardphysics_pipeline.render_efficiency import build_surface_gaussians
from standardphysics_pipeline.textures.camera import load_cameras
from standardphysics_pipeline.textures.scan_colour import colour_the_scan, scan_geometry, unused_vertices_removed

MAX_PHOTO_EDGE = 1600


def _photo(path: Path) -> np.ndarray:
    with Image.open(path) as opened:
        image = opened.convert("RGB")
        image.thumbnail((MAX_PHOTO_EDGE, MAX_PHOTO_EDGE), Image.Resampling.LANCZOS)
        return np.asarray(image, dtype=np.float32) / 255.0


def _evenly_spread(cameras, limit):
    if len(cameras) <= limit:
        return cameras
    picks = np.linspace(0, len(cameras) - 1, limit).round().astype(int)
    return [cameras[index] for index in dict.fromkeys(picks.tolist())]


def _sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("room", choices=list(CAPTURES))
    parser.add_argument("--captures", type=Path, default=Path("datasets/phone/moffett"))
    parser.add_argument("--output", type=Path, default=Path("runs/moffett/render-efficiency"))
    parser.add_argument("--spacing", type=float, default=0.02)
    parser.add_argument("--max-samples", type=int, default=150000)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--opacity", type=float, default=0.5)
    parser.add_argument("--tangent-factor", type=float, default=0.75)
    parser.add_argument("--normal-ratio", type=float, default=0.1)
    parser.add_argument("--cameras", type=int, default=60)
    parser.add_argument("--tag", type=str, default="", help="Suffix for the output directory, so repeats do not collide")
    args = parser.parse_args()

    started = time.monotonic()
    directory = args.captures / CAPTURES[args.room]
    c2r = capture_to_room_from_payload(json.loads((directory / "room.json").read_text()))
    vertices, triangles = scan_geometry(directory / "lidar-mesh.json", c2r)

    poses = json.loads((directory / "poses.json").read_text())
    frame_paths = {p["frame_id"]: directory / "frames" / Path(p["image"]).name for p in poses}
    cameras = [
        camera for camera in load_cameras(directory / "poses.json", frame_paths, c2r)
        if frame_paths.get(camera.frame_id, Path()).is_file()
    ]
    cameras = _evenly_spread(cameras, args.cameras)
    if not cameras:
        raise SystemExit("no stored photo has a usable camera pose")

    resized = [camera.resized(*_photo(frame_paths[camera.frame_id]).shape[1::-1]) for camera in cameras]
    images = [_photo(frame_paths[camera.frame_id]) for camera in cameras]
    coloured = unused_vertices_removed(colour_the_scan(vertices, triangles, resized, images))

    result = build_surface_gaussians(
        coloured.vertices,
        coloured.triangles,
        coloured.colours,
        spacing=args.spacing,
        tangent_factor=args.tangent_factor,
        normal_ratio=args.normal_ratio,
        opacity=args.opacity,
        seed=args.seed,
        max_samples=args.max_samples,
    )

    folder = f"surface-splats-s{args.seed}" + (f"-{args.tag}" if args.tag else "")
    out_dir = args.output / args.room / folder
    ply = out_dir / "surface-splats.ply"
    result.gaussians.export_ply(ply)

    provenance = {
        "room": args.room,
        "capture_id": CAPTURES[args.room],
        "method": "deterministic_surface_gaussians",
        "geometry_only": result.gaussians.geometry_only,
        "coordinate_system": "scene Z up, metres",
        "splat_count": len(result.gaussians),
        "supported_count": result.supported_count,
        "rejected_count": result.rejected_count,
        "config": {
            "seed": args.seed,
            "spacing_m": args.spacing,
            "max_samples": args.max_samples,
            "opacity": args.opacity,
            "tangent_factor": args.tangent_factor,
            "normal_ratio": args.normal_ratio,
            "camera_count": len(cameras),
        },
        "color_source": "best-view per-vertex photo sampling (colour_the_scan), sRGB",
        "centre_constraint": "fixed on measured LiDAR surface",
        "input_hashes": {
            "lidar_mesh_sha256": _sha256(directory / "lidar-mesh.json"),
            "poses_sha256": _sha256(directory / "poses.json"),
        },
        "output_sha256": _sha256(ply),
        "wall_seconds": round(time.monotonic() - started, 3),
        "note": "rendering parameters, not measurement accuracy",
    }
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
