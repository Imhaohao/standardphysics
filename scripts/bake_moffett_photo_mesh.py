"""Offline photographic surface bake of one preserved Moffett capture.

Outputs a local-room GLB and coverage manifest. This does not publish an
unverified alignment or modify the original measured geometry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import photo_mesh_glb
import trimesh
from moffett_image_registration import CAPTURES
from PIL import Image
from standardphysics_pipeline.ingest import capture_to_room_from_payload
from standardphysics_pipeline.textures.camera import load_cameras
from standardphysics_pipeline.textures.scan_colour import scan_geometry
from standardphysics_pipeline.textures.surface_photos import choose_views, choose_views_partial, snap_to_measured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("room", choices=CAPTURES)
    parser.add_argument("--captures", type=Path, default=Path("datasets/phone/moffett"))
    parser.add_argument("--output", type=Path, default=Path("runs/moffett/photo-surfaces"))
    parser.add_argument("--faces", type=int, default=250000)
    parser.add_argument("--cameras", type=int, default=160)
    parser.add_argument("--visibility-width", type=int, default=1280)
    parser.add_argument("--partial", action="store_true",
                        help="allow partial face support (>=5 of 7 samples visible) instead of all corners")
    parser.add_argument("--min-facing", type=float, default=0.2,
                        help="facing threshold for partial selection (default 0.2)")
    parser.add_argument("--display-depth", action="store_true",
                        help="run occlusion checks on the display mesh instead of the full geometry")
    parser.add_argument("--no-centre", action="store_true",
                        help="partial rule without the centre-sample requirement (spread condition still applies)")
    parser.add_argument("--snap", action="store_true",
                        help="snap display vertices back onto the measured full-resolution surface")
    parser.add_argument("--exclude-frame", action="append", default=[], metavar="FRAME_ID",
                        help="exclude this captured frame from source selection; repeat to exclude several")
    parser.add_argument("--exclude-from", type=Path, default=None, metavar="FILE",
                        help="file of line-separated frame IDs to exclude from source selection")
    args = parser.parse_args()
    directory = args.captures/CAPTURES[args.room]
    output = args.output/args.room
    output.mkdir(parents=True, exist_ok=True)
    c2r = capture_to_room_from_payload(json.loads((directory/"room.json").read_text()))
    vertices, triangles = scan_geometry(directory/"lidar-mesh.json", c2r)
    mesh_sha = hashlib.sha256((directory/"lidar-mesh.json").read_bytes()).hexdigest()[:12]
    room_sha = hashlib.sha256((directory/"room.json").read_bytes()).hexdigest()[:12]
    cache = output/f"display-{mesh_sha}-{room_sha}-{args.faces}.npz"
    excluded_frames = set(args.exclude_frame)
    if args.exclude_from is not None:
        excluded_frames |= {line.strip() for line in args.exclude_from.read_text().splitlines() if line.strip()}
    if cache.exists():
        saved = np.load(cache)
        display_vertices, display_triangles = saved["vertices"], saved["triangles"]
    else:
        mesh = trimesh.Trimesh(vertices, triangles, process=False)
        reduced = mesh.simplify_quadric_decimation(face_count=args.faces)
        display_vertices, display_triangles = reduced.vertices, reduced.faces
        np.savez_compressed(cache, vertices=display_vertices, triangles=display_triangles)
    print(args.room, "display triangles", len(display_triangles), flush=True)
    snap_status = None
    if args.snap:
        display_vertices, snap_count, snap_max = snap_to_measured(display_vertices, vertices)
        snap_status = {"snapped_vertices": snap_count, "max_snap_distance_m": float(snap_max)}
        print(f"snapped {snap_count} display vertices; max distance {snap_max:.3f} m", flush=True)
    poses = json.loads((directory/"poses.json").read_text())
    frames = {p["frame_id"]: directory/"frames"/Path(p["image"]).name for p in poses}
    cameras = load_cameras(directory/"poses.json", frames, c2r)
    cameras = [camera for camera in cameras if camera.frame_id not in excluded_frames]
    if not cameras:
        raise ValueError("no source cameras remain after --exclude-frame/--exclude-from")
    cameras = [cameras[i] for i in np.linspace(0, len(cameras)-1, min(args.cameras, len(cameras)), dtype=int)]
    small = [c.resized(args.visibility_width, round(c.height*args.visibility_width/c.width)) for c in cameras]

    def progress(current, count, fraction):
        if current % 10 == 0 or current == count:
            print(f"{args.room}: {current}/{count} views, photographed surface {fraction:.1%}", flush=True)

    depth_vertices = None if args.display_depth else vertices
    depth_triangles = None if args.display_depth else triangles
    if args.partial:
        assignment, areas = choose_views_partial(
            display_vertices, display_triangles, small, depth_vertices, depth_triangles, progress,
            min_facing=args.min_facing, centre_required=not args.no_centre)
    else:
        assignment, areas = choose_views(
            display_vertices, display_triangles, small, depth_vertices, depth_triangles, progress)
    np.savez_compressed(output/"view-assignment.npz", camera_index=assignment, face_area_m2=areas)
    builder = photo_mesh_glb.GlbBuilder()
    builder.add_neutral_material((158/255, 153/255, 148/255))
    used = []
    for index in np.unique(assignment):
        faces = display_triangles[assignment == index]
        points = display_vertices[faces.ravel()]
        geometry = np.column_stack([points[:, 0], points[:, 2], -points[:, 1]])
        if index < 0:
            builder.add_neutral_mesh(geometry, np.arange(len(points)).reshape(-1, 3), f"{args.room}:{index}")
        else:
            camera = cameras[index]
            image_path = frames[camera.frame_id]
            photo = Image.open(image_path).convert("RGB")
            camera = camera.resized(*photo.size)
            u, v, _ = camera.project(points)
            left = max(0, int(np.floor(u.min()))-2)
            top = max(0, int(np.floor(v.min()))-2)
            right = min(photo.width, int(np.ceil(u.max()))+3)
            bottom = min(photo.height, int(np.ceil(v.max()))+3)
            photo = photo.crop((left, top, right, bottom))
            uv = np.column_stack([(u-left+.5)/photo.width, (v-top+.5)/photo.height])
            builder.add_textured_mesh(geometry, np.arange(len(points)).reshape(-1, 3), uv,
                                      np.asarray(photo, dtype=np.uint8), f"{args.room}:{index}")
            used.append({"frame_id": camera.frame_id, "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                         "crop_pixels": [left, top, right, bottom], "triangles": len(faces)})
    glb = output/"photo-mesh.glb"
    glb.write_bytes(builder.build())
    manifest = {"room": args.room, "capture_id": CAPTURES[args.room], "capture_to_room": c2r.m,
                "vertex_snap": snap_status,
                "coordinate_system": "GLTF Y up: (scene X, scene Z, -scene Y)",
                "selection": (f"choose_views_partial (>=5/7 samples + spread, min_facing={args.min_facing}, "
                               f"centre={'required' if not args.no_centre else 'not required'}, "
                               f"depth_reference={'display' if args.display_depth else 'full geometry'})")
                if args.partial else "choose_views (all corners and centre, full geometry depth)",
                "camera_count": int(args.cameras),
                "excluded_frames": sorted(excluded_frames),
                "source_mesh_sha256": hashlib.sha256((directory/"lidar-mesh.json").read_bytes()).hexdigest(),
                "source_poses_sha256": hashlib.sha256((directory/"poses.json").read_bytes()).hexdigest(),
                "display_triangle_count": len(display_triangles), "display_only_decimation": True,
                "photographed_area_fraction": float(areas[assignment >= 0].sum()/areas.sum()),
                "unseen_surface": "neutral grey; no generated detail", "frames": used,
                "glb_bytes": glb.stat().st_size, "glb_sha256": hashlib.sha256(glb.read_bytes()).hexdigest()}
    (output/"photo-mesh.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(glb, glb.stat().st_size, "bytes", flush=True)


if __name__ == "__main__":
    main()
