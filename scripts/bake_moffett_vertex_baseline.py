"""Vertex-colour baseline of the center capture on the same display mesh the
photo-mesh candidates use, so baseline comparisons share geometry.

Uses the existing scan_colour path (per-vertex photo colour, unlit). Depth
occlusion here uses the display mesh itself; the photo-mesh baselines check
against the full geometry. That allowance difference is recorded in the
manifest instead of being silently conflated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from moffett_image_registration import CAPTURES
from standardphysics_pipeline.ingest import capture_to_room_from_payload
from standardphysics_pipeline.textures.camera import load_cameras
from standardphysics_pipeline.textures.scan_colour import (
    MAX_PHOTO_EDGE,
    colour_the_scan,
    unused_vertices_removed,
    write_scan_glb,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("room", choices=CAPTURES)
    parser.add_argument("--captures", type=Path, default=Path("datasets/phone/moffett"))
    parser.add_argument("--display", type=Path,
                        default=Path("runs/moffett/photo-mesh-500/r001/baselines/center/display-250000.npz"))
    parser.add_argument("--output", type=Path, default=Path("runs/moffett/photo-mesh-500/r001/baselines/center"))
    parser.add_argument("--photos", type=int, default=60)
    args = parser.parse_args()
    directory = args.captures / CAPTURES[args.room]
    args.output.mkdir(parents=True, exist_ok=True)
    c2r = capture_to_room_from_payload(json.loads((directory / "room.json").read_text()))
    display = np.load(args.display)
    vertices, triangles = display["vertices"], display["triangles"]
    poses = json.loads((directory / "poses.json").read_text())
    frames = {p["frame_id"]: directory / "frames" / Path(p["image"]).name for p in poses}
    cameras = [camera for camera in load_cameras(directory / "poses.json", frames, c2r)
               if frames.get(camera.frame_id, Path()).is_file()]
    picks = np.linspace(0, len(cameras) - 1, args.photos).round().astype(int)
    cameras = [cameras[i] for i in dict.fromkeys(picks.tolist())]
    from PIL import Image

    resized, images = [], []
    for camera in cameras:
        photo = Image.open(frames[camera.frame_id]).convert("RGB")
        photo.thumbnail((MAX_PHOTO_EDGE, MAX_PHOTO_EDGE), Image.Resampling.LANCZOS)
        resized.append(camera.resized(*photo.size))
        images.append(np.asarray(photo, dtype=np.float32) / 255.0)
    started = time.monotonic()
    scan = unused_vertices_removed(colour_the_scan(vertices, triangles, resized, images))
    out_path = args.output / "vertex-colour.glb"
    write_scan_glb(scan, out_path)
    manifest = {
        "room": args.room, "capture_id": CAPTURES[args.room],
        "display_cache": str(args.display),
        "display_triangle_count": int(len(triangles)),
        "photos": len(cameras),
        "painted_fraction": float(scan.seen.mean()),
        "depth_occlusion": "display mesh only",
        "allowance_note": "photo-mesh baselines occlude against full geometry; this baseline uses its own display depth",
        "glb_bytes": out_path.stat().st_size,
        "glb_sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "seconds": round(time.monotonic() - started, 1),
    }
    (args.output / "vertex-colour.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
