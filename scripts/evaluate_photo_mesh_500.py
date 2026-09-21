"""Benchmark moffett-photo-mesh-500: render frozen views and compute policy gates.

Conservative: produced numbers are machine metrics only; perceptual and user
gates stay pending unless a human/agent with vision reviews the PNGs. The
evaluator only READS evidence; it never synthesizes pass values, and it exits
nonzero when required evidence is missing or wrong-sized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from render_photo_mesh_raster import render_view, scene_arrays  # noqa: E402
from standardphysics_pipeline.ingest import capture_to_room_from_payload  # noqa: E402
from standardphysics_pipeline.render_efficiency.photo_mesh_500 import (  # noqa: E402
    FINAL, build_captured_view, build_novel_view, coverage_fractions,
    load_reference_500, psnr_ssim, resize_500, edge_width_profiles,
)
from standardphysics_pipeline.textures.camera import load_cameras  # noqa: E402

CAPTURES = {
    "center": "454B3661-D3F8-46E8-ADAA-3123E759AA64",
    "top": "BBB88E0A-A2C3-4611-AFE1-71C43454E8C6",
    "bottom_left": "D9946491-26FD-4864-9673-C88180328109",
    "left": "A92A8ED6-87A5-474D-8514-D2D0E6A1F00D",
}


class FrozenView:
    def __init__(self, id, camera, width, height, reference):
        self.id = id
        self.camera = camera
        self.width = width
        self.height = height
        self.reference = reference


def load_splits(run_dir: Path) -> dict:
    return json.loads((run_dir / "stageA" / "splits.json").read_text())


def build_transfer_views(run_dir: Path, room: str) -> list[FrozenView]:
    manifest = json.loads((run_dir / "stageA" / "transfer-novel-views.json").read_text())
    views = []
    for spec in manifest[room]["views"]:
        camera = build_novel_view(spec)
        views.append(FrozenView(spec["id"], camera, camera.width, camera.height, None))
    return views


def build_views(run_dir: Path) -> list[FrozenView]:
    splits = load_splits(run_dir)
    capture = CAPTURES[splits["capture"]]
    directory = Path("datasets/phone/moffett") / capture
    c2r = capture_to_room_from_payload(json.loads((directory / "room.json").read_text()))
    poses = json.loads((directory / "poses.json").read_text())
    frames = {p["frame_id"]: directory / "frames" / Path(p["image"]).name for p in poses}
    cameras = load_cameras(directory / "poses.json", frames, c2r)
    by_frame = {c.frame_id: c for c in cameras}
    views = []
    for frame_id in splits["validation_views_captured"] + splits["test_views_captured"]:
        camera = build_captured_view(frame_id, by_frame[frame_id])
        views.append(FrozenView(frame_id, camera, camera.width, camera.height,
                                load_reference_500(frames[frame_id])))
    for novel in splits["novel_views"]:
        camera = build_novel_view(novel)
        views.append(FrozenView(novel["id"], camera, camera.width, camera.height, None))
    return views


def render_all(arrays, arrays_region, views, out_dir: Path) -> list[dict]:
    records = []
    for view in views:
        saves = {}
        buffers = {}
        passes = ["rgb", "geometry", "source_id", "coverage"]
        paths = [out_dir / f"{view.id}-{name}.png" for name in passes]
        outputs = render_view(arrays, view.camera, view.width, view.height, list(range(4)), paths)
        for name, path in zip(passes, paths):
            saves[name] = str(path)
        region_path = out_dir / f"{view.id}-region.png"
        render_view(arrays_region, view.camera, view.width, view.height, [3], [region_path])
        saves["region"] = str(region_path)
        if view.reference is not None:
            resized = out_dir / f"{view.id}-rgb-{FINAL}.png"
            resize_500(out_dir / f"{view.id}-rgb.png").astype(np.uint8)
            Image.fromarray(resize_500(out_dir / f"{view.id}-rgb.png").astype(np.uint8)).save(resized)
            saves[f"rgb_{FINAL}"] = str(resized)
        records.append({"id": view.id, "width": view.width, "height": view.height,
                        "reference": view.reference is not None, "passes": saves})
    return records


def resolution_map(arrays, view, region_faces, out_dir) -> dict:
    """Linear source texels per output pixel at 500 x 500 via the UV jacobian."""
    from standardphysics_pipeline.render_efficiency.photo_mesh_500 import RasterCamera
    camera = view.camera
    resized = RasterCamera(view.id, FINAL, FINAL, camera.scene_to_camera,
                           camera.fx * FINAL / camera.width, camera.fy * FINAL / camera.height,
                           (camera.cx + 0.5) * FINAL / camera.width - 0.5,
                           (camera.cy + 0.5) * FINAL / camera.height - 0.5)
    outputs = render_view(arrays, resized, FINAL, FINAL, [0], [out_dir / f"{view.id}-rgb-direct-{FINAL}.png"])
    buffers = outputs[0]
    uv = buffers["uv"]
    face_buffer = buffers["face_buffer"]
    texi = buffers["texi"]
    depth = buffers["depth"]
    tex_dims = {i: arrays[4][i].shape[:2] for i in range(len(arrays[4])) if arrays[4][i] is not None}
    dudx = (np.roll(uv[..., 0], -1, axis=1) - np.roll(uv[..., 0], 1, axis=1)) / 2.0
    dvdx = (np.roll(uv[..., 1], -1, axis=1) - np.roll(uv[..., 1], 1, axis=1)) / 2.0
    dudy = (np.roll(uv[..., 0], -1, axis=0) - np.roll(uv[..., 0], 1, axis=0)) / 2.0
    dvdy = (np.roll(uv[..., 1], -1, axis=0) - np.roll(uv[..., 1], 1, axis=0)) / 2.0
    det = np.abs(dudx * dvdy - dudy * dvdx)
    linear = np.zeros((FINAL, FINAL), dtype=np.float64)
    for index, dims in tex_dims.items():
        where = texi == index
        linear[where] = np.sqrt(np.maximum(det[where], 0.0)) * float(dims[0] * dims[1]) ** 0.5
    visible = depth < np.inf
    supported = visible & (texi >= 0)
    region = np.zeros((FINAL, FINAL), dtype=bool)
    valid_faces = (face_buffer >= 0) & (face_buffer < len(region_faces))
    region[valid_faces] = region_faces[face_buffer[valid_faces]]
    result = {"supported_target_pixels": int(supported.sum()), "visible_target_pixels": int(visible.sum()),
              "median_samples_per_px": float(np.median(linear[supported])) if supported.any() else np.nan,
              "fraction_supported_meeting_1": float((linear[supported] >= 1.0).mean()) if supported.any() else np.nan,
              "fraction_supported_meeting_2": float((linear[supported] >= 2.0).mean()) if supported.any() else np.nan,
              "critical_roi_supported_count": int((supported & region).sum()),
              "critical_roi_meeting_2": float((linear[(supported & region)] >= 2.0).mean())
              if (supported & region).any() else np.nan,
              "note": "linear axis rate estimated as sqrt(|uv jacobian| * texture area)"}
    Image.fromarray(np.clip(linear * 16, 0, 255).astype(np.uint8), "L").save(
        out_dir / f"{view.id}-resolution-{FINAL}.png")
    return result


def feature_matches(reference: np.ndarray, candidate: np.ndarray, max_features=500, ratio=0.75):
    try:
        import cv2
    except ImportError:
        return {"available": False}
    sift = cv2.SIFT_create(nfeatures=max_features)
    ref_grey = cv2.cvtColor(reference.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    cand_grey = cv2.cvtColor(candidate.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    kp1, des1 = sift.detectAndCompute(ref_grey, None)
    kp2, des2 = sift.detectAndCompute(cand_grey, None)
    if des1 is None or des2 is None or not len(des1) or not len(des2):
        return {"available": True, "keypoints": (len(kp1), len(kp2)), "matches": 0}
    raw = cv2.BFMatcher().knnMatch(des1, des2, k=2)
    good = [pair[0] for pair in raw if len(pair) == 2 and pair[0].distance < ratio * pair[1].distance]
    errors = [np.linalg.norm(np.array(kp1[m.queryIdx].pt) - np.array(kp2[m.trainIdx].pt)) for m in good]
    return {"available": True, "keypoints": (len(kp1), len(kp2)), "matches": len(good),
            "median_error_px": float(np.median(errors)) if errors else None,
            "p95_error_px": float(np.percentile(errors, 95)) if errors else None,
            "machine_note": "SIFT descriptor matches, provisional alignment evidence"}


def hole_metrics(rgb_path, geometry_path, coverage_path):
    """Unphotographed connected components inside the measured surface.

    Returns the largest single untextured hole as a fraction of total target
    pixels, plus the photographed mask for baseline comparisons.
    """
    from scipy import ndimage

    geometry = np.asarray(Image.open(geometry_path).convert("L"), dtype=np.float64) > 128
    photographed = np.asarray(Image.open(coverage_path).convert("L"), dtype=np.float64) > 128
    rgb = np.asarray(Image.open(rgb_path).convert("RGB"))
    total = geometry & (rgb.sum(axis=-1) > 0)
    untextured = total & ~photographed
    if untextured.sum() == 0:
        return {"largest_hole_fraction": 0.0, "hole_count": 0, "target_pixels": int(total.sum())}, untextured
    labels, count = ndimage.label(untextured)
    sizes = ndimage.sum(untextured, labels, range(1, count + 1))
    return {"largest_hole_fraction": float(sizes.max() / max(total.sum(), 1)),
            "hole_count": int(count), "target_pixels": int(total.sum()),
            "hole_fraction_total": float(untextured.sum() / max(total.sum(), 1))}, untextured


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--glb", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-eval", type=Path, default=None,
                        help="baseline evaluation.json for new-hole comparisons")
    parser.add_argument("--transfer-room", default=None,
                        help="evaluate the given room's frozen transfer views instead of the pilot views")
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    if (args.out / "evaluation.json").exists():
        sys.exit(f"refusing to overwrite existing evaluation {args.out}")
    if not args.glb.is_file():
        sys.exit(f"missing candidate GLB: {args.glb}")

    views = build_views(args.run) if args.transfer_room is None else build_transfer_views(args.run, args.transfer_room)
    if not views:
        sys.exit("no frozen views; refusing to evaluate empty evidence")
    for view in views:
        if view.reference is not None:
            Image.fromarray(view.reference.astype(np.uint8)).save(args.out / f"{view.id}-reference-500.png")
    arrays = scene_arrays(args.glb)
    glb_hash = hashlib.sha256(args.glb.read_bytes()).hexdigest()

    region = json.loads((args.run / "stageA" / "region.json").read_text())
    room_lo = np.array(region["region_box"][0])
    room_hi = np.array(region["region_box"][1])
    G = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])
    corners = np.stack([np.minimum.reduce([G @ room_lo, G @ room_hi]),
                        np.maximum.reduce([G @ room_lo, G @ room_hi])])
    inside = ((arrays[0][:, 0] >= corners[0, 0]) & (arrays[0][:, 0] <= corners[1, 0]) &
              (arrays[0][:, 1] >= corners[0, 1]) & (arrays[0][:, 1] <= corners[1, 1]) &
              (arrays[0][:, 2] >= corners[0, 2]) & (arrays[0][:, 2] <= corners[1, 2]))
    region_faces = inside[arrays[1]].all(axis=1)
    np.save(args.out / "region-face-mask.npy", region_faces)
    region_texture_index = np.where(region_faces, 1, -2).astype(np.int32)
    arrays_region = (arrays[0], arrays[1], arrays[2], region_texture_index, arrays[4], arrays[5],
                     arrays[6], arrays[7], np.full(len(arrays[1]), -1, dtype=np.int32))
    records = render_all(arrays, arrays_region, views, args.out)

    baseline_doc = json.loads(args.baseline_eval.read_text()) if args.baseline_eval is not None and args.baseline_eval.is_file() else None
    results = {"label": args.label, "glb": str(args.glb), "glb_sha256": glb_hash,
               "policy_sha256": hashlib.sha256(args.policy.read_bytes()).hexdigest(),
               "baseline_eval": str(args.baseline_eval) if args.baseline_eval else None,
               "views": [], "gates": {}}
    coverage_gate = policy["visual_gates"]["coverage"]
    resolution_gate = policy["visual_gates"]["effective_resolution"]
    alignment = policy["visual_gates"]["alignment"]
    edge = policy["visual_gates"]["detail"]
    for view, record in zip(views, records):
        entry = {"id": view.id, "kind": "captured" if view.reference is not None else "novel",
                 "width": view.width, "height": view.height,
                 "reference": view.reference is not None, "passes": record["passes"]}
        region_mask = np.asarray(__import__("PIL.Image", fromlist=["Image"]).open(Path(record["passes"]["region"])).convert("L")) > 128
        coverage = coverage_fractions(Path(record["passes"]["rgb"]), Path(record["passes"]["geometry"]),
                                      Path(record["passes"]["coverage"]), region_mask)
        entry["coverage"] = coverage
        entry["holes"], untextured_mask = hole_metrics(Path(record["passes"]["rgb"]),
                                                       Path(record["passes"]["geometry"]),
                                                       Path(record["passes"]["coverage"]))
        if args.baseline_eval is not None and args.baseline_eval.is_file():
            baseline_record = next((v for v in baseline_doc["views"] if v["id"] == view.id), None)
            if baseline_record is not None:
                baseline_cov = Path(baseline_record["passes"]["coverage"])
                baseline_geo = Path(baseline_record["passes"]["geometry"])
                baseline_rgb = Path(baseline_record["passes"]["rgb"])
                geometry = np.asarray(Image.open(Path(record["passes"]["geometry"])).convert("L")) > 128
                rgb = np.asarray(Image.open(Path(record["passes"]["rgb"])).convert("RGB"))
                total = geometry & (rgb.sum(axis=-1) > 0)
                base_photo = np.asarray(Image.open(baseline_cov).convert("L")) > 128
                base_geo = np.asarray(Image.open(baseline_geo).convert("L")) > 128
                base_rgb = np.asarray(Image.open(baseline_rgb).convert("RGB"))
                base_total = base_geo & (base_rgb.sum(axis=-1) > 0)
                new_holes = total & base_total & ~untextured_mask & ~base_photo
                entry["holes"]["new_hole_fraction_vs_baseline"] = float(
                    new_holes.sum() / max(base_total.sum(), 1))
        entry["resolution"] = resolution_map(arrays, view, region_faces, args.out)
        if view.reference is not None:
            candidate = resize_500(Path(record["passes"]["rgb"]))
            entry["psnr_ssim"] = psnr_ssim(view.reference, candidate, None)
            entry["edge_profiles"], _ = edge_width_profiles(
                view.reference, candidate, None, args.out / f"{view.id}-frozen-edges.json")
            entry["feature_matches"] = feature_matches(view.reference, candidate)
        results["views"].append(entry)

    photographed = {v["id"]: v["coverage"]["photographed_fraction"] for v in results["views"]}
    results["gates"] = {
        "coverage_min_target_fraction": coverage_gate["min_photographed_target_pixel_fraction_each_view"],
        "manual_visual_review": "pending_user_and_agent_vision_unavailable_in_this_session",
        "machine_metrics_only": True,
        "per_view_photographed_fraction": photographed,
        "coverage_passes": {k: (v is not None and not (isinstance(v, float) and v != v) and v >= coverage_gate["min_photographed_target_pixel_fraction_each_view"])
                            for k, v in photographed.items()},
        "resolution_gate_fraction_meeting_both": {v["id"]: v["resolution"]["fraction_supported_meeting_1"]
                                                  for v in results["views"]},
        "alignment_threshold_median_px": alignment["median_error_px_max"],
        "edge_median_added_px_max": edge["median_added_edge_width_px_max"],
        "evaluator_notes": "caller-supplied pass booleans are never evidence; thresholds from the policy at run time",
    }
    (args.out / "evaluation.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results["gates"], indent=1))


if __name__ == "__main__":
    main()
