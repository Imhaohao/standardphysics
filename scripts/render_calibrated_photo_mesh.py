"""Re-render an existing room GLB using the bake's complete camera calibration.

Does not rebake, refine poses, publish or overwrite. Output is a fresh directory.
Blender verifies corners at three depths before rendering any actual views.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import standardphysics_pipeline
from PIL import Image
from standardphysics_contracts import Mat4
from standardphysics_pipeline.textures.blender_camera import blender_view
from standardphysics_pipeline.textures.camera import load_cameras


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(args):
    manifest = json.loads(args.glb.with_suffix(".json").read_text())
    if manifest["glb_sha256"] != digest(args.glb):
        raise ValueError("GLB does not match the bake manifest")
    poses_path = args.capture/"poses.json"
    if manifest["source_poses_sha256"] != digest(poses_path):
        raise ValueError("pose file does not match the bake manifest")
    transform = Mat4(m=manifest["capture_to_room"])
    if len(set(args.frames)) != len(args.frames):
        raise ValueError("duplicate requested frame IDs")
    cameras = load_cameras(poses_path, args.frames, transform)
    if {camera.frame_id for camera in cameras} != set(args.frames):
        raise ValueError("some requested frames lack projectable calibration")
    records = {pose["frame_id"]: pose for pose in json.loads(poses_path.read_text())}
    args.out.mkdir(parents=True, exist_ok=False)
    views = []
    for camera in cameras:
        source = args.capture/"frames"/Path(records[camera.frame_id]["image"]).name
        with Image.open(source) as image:
            if image.size != (camera.width, camera.height):
                raise ValueError(f"{camera.frame_id}: image and camera dimensions disagree")
            side = min(image.size)
            left, top = (image.width-side)//2, (image.height-side)//2
            crop = (left, top, left+side, top+side)
            view = blender_view(camera, crop, (args.size, args.size))
            view["source"] = str(source.resolve())
            view["source_sha256"] = digest(source)
            image.convert("RGB").crop(crop).resize((args.size, args.size), Image.Resampling.LANCZOS).save(
                args.out/f"{camera.frame_id}_source.png")
            views.append(view)
    return {"glb": str(args.glb.resolve()), "glb_sha256": manifest["glb_sha256"],
            "source_poses_sha256": manifest["source_poses_sha256"],
            "coordinate_system": "Blender default glTF import restores Z-up room coordinates",
            "purpose": "calibration diagnostic; not full benchmark acceptance",
            "reference_resample": "LANCZOS", "views": views}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glb", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--frames", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--size", type=int, default=500)
    parser.add_argument("--blender", default="/Applications/Blender.app/Contents/MacOS/Blender")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if args.size <= 0 or args.timeout <= 0:
        parser.error("size and timeout must be positive")
    plan = prepare(args)
    script = Path(standardphysics_pipeline.__file__).parent/"blender_scripts/render_calibrated_mesh.py"
    adapter = Path(standardphysics_pipeline.__file__).parent/"textures/blender_camera.py"
    plan["code_sha256"] = {str(path): digest(path) for path in (Path(__file__), script, adapter)}
    (args.out/"code").mkdir()
    for path in (Path(__file__), script, adapter):
        (args.out/"code"/path.name).write_bytes(path.read_bytes())
    plan_path = args.out/"render-plan.json"
    plan_path.write_text(json.dumps(plan, indent=2)+"\n")
    with (args.out/"blender.log").open("w") as log:
        result = subprocess.run([args.blender, "-b", "--factory-startup", "--python-exit-code", "1",
                                 "-P", str(script), "--", str(plan_path.resolve())],
                                stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
    if result.returncode or "CALIBRATED_MESH_RENDER_COMPLETE" not in (args.out/"blender.log").read_text():
        raise RuntimeError(f"render failed: see {args.out/'blender.log'}")
    outputs = {}
    coverage = []
    for view in plan["views"]:
        for suffix in ("candidate", "geometry", "photo_support"):
            path = args.out/f"{view['id']}_{suffix}.png"
            with Image.open(path) as image:
                if image.size != (args.size, args.size):
                    raise RuntimeError(f"incorrect output dimensions: {path}")
            outputs[path.name] = digest(path)
        geometry = np.asarray(Image.open(args.out/f"{view['id']}_geometry.png").convert("L")) > 128
        photographed = np.asarray(Image.open(args.out/f"{view['id']}_photo_support.png").convert("L")) > 128
        coverage.append({"id": view["id"], "geometry_pixels": int(geometry.sum()),
                         "photographed_pixels": int((photographed & geometry).sum()),
                         "fraction": float((photographed & geometry).sum()/geometry.sum()) if geometry.any() else None})
    (args.out/"support-diagnostic.json").write_text(json.dumps({"views": coverage,
        "scope": "Visible candidate display mesh only; not frozen full measured geometry or verified source visibility",
        "benchmark_coverage_pass": None}, indent=2)+"\n")
    (args.out/"completed.json").write_text(json.dumps({"outputs": outputs,
        "plan_sha256": digest(plan_path), "verification_sha256": digest(args.out/"camera-verification.json"),
        "blender_exit_code": result.returncode, "quality_accepted": False}, indent=2)+"\n")
    print(args.out)


if __name__ == "__main__":
    main()
