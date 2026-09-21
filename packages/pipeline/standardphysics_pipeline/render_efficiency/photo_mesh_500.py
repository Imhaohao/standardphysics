"""Benchmark plumbing for moffett-photo-mesh-500: cameras, references, metrics.

Camera convention: pixel frame (+X right, +Y down, +Z forward) in the *GLTF
scene frame*. GLTFs are written in scene = G * room with G = (x, z, -y), so a
room-frame camera (R_room, t) becomes (R_room @ G.T, t).

All captured views render at the pristine square-crop resolution (1440 x 1440,
native pixel scale) and BOTH the render and the photographic reference are
resized to 500 x 500 with the same PIL bilinear resample.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np
from PIL import Image

FRAME_SCENE = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
"""Scene point = FRAME_SCENE @ room point (matches bake writes (x, z, -y))."""

CAPTURE_RENDER = {"width": 1440, "height": 1440}
FINAL = 500
FILTER = Image.Resampling.BILINEAR
CROP_LEFT = 240


@dataclasses.dataclass(frozen=True)
class RasterCamera:
    id: str
    width: int
    height: int
    scene_to_camera: np.ndarray
    fx: float
    fy: float
    cx: float
    cy: float


def room_to_scene_rotation(room_to_camera: np.ndarray) -> np.ndarray:
    return room_to_camera[:3, :3] @ FRAME_SCENE.T


def camera_from_room(id: str, room_to_camera: np.ndarray, fx, fy, cx, cy, width, height) -> RasterCamera:
    return RasterCamera(id, width, height, np.column_stack([room_to_scene_rotation(room_to_camera),
                                                            room_to_camera[:3, 3]]), fx, fy, cx, cy)


def build_captured_view(frame_id: str, camera, crop_left: int = CROP_LEFT) -> RasterCamera:
    """Square central crop keeps the native pixel scale: only cx shifts by the crop."""
    return camera_from_room(frame_id, camera.room_to_camera, camera.fx, camera.fy,
                            camera.cx - crop_left, camera.cy, CAPTURE_RENDER["width"], CAPTURE_RENDER["height"])


def build_novel_view(spec: dict) -> RasterCamera:
    room_to_camera = np.asarray(spec["room_to_camera"], dtype=np.float64).reshape(4, 4)
    return camera_from_room(spec["id"], room_to_camera, spec["fx"], spec["fy"], spec["cx"], spec["cy"],
                            spec["width"], spec["height"])


def square_crop_resize(image: Image.Image, width: int = CAPTURE_RENDER["width"]) -> Image.Image:
    return image.crop((CROP_LEFT, 0, CROP_LEFT + width, width))


def load_reference_500(frame_path: Path) -> np.ndarray:
    image = Image.open(frame_path).convert("RGB")
    cropped = square_crop_resize(image)
    return np.asarray(cropped.resize((FINAL, FINAL), FILTER), dtype=np.float64)


def resize_500(path: Path) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    if image.size != (FINAL, FINAL):
        image = image.resize((FINAL, FINAL), FILTER)
    return np.asarray(image, dtype=np.float64)


def visible_geometry_mask(geometry_pass_path: Path) -> np.ndarray:
    return np.asarray(Image.open(geometry_pass_path).convert("L"), dtype=np.float64) > 128


def coverage_fractions(rgb_path, geometry_path, coverage_path, region_mask=None):
    geometry = visible_geometry_mask(geometry_path)
    if not geometry.any():
        return {"target_pixels": 0, "photographed_fraction": np.nan, "critical_roi_fraction": np.nan,
                "note": "no visible geometry"}
    photographed = np.asarray(Image.open(coverage_path).convert("L"), dtype=np.float64) > 128
    stale = np.asarray(Image.open(rgb_path).convert("RGB"))
    total = geometry & (stale.sum(axis=-1) > 0)
    frac = photograph_frac(photographed, total)
    result = {"target_pixels": int(total.sum()), "photographed_fraction": frac}
    if region_mask is not None:
        result["critical_roi_fraction"] = photograph_frac(np.asarray(region_mask, dtype=bool) & photographed,
                                                          np.asarray(region_mask, dtype=bool) & total)
    else:
        result["critical_roi_fraction"] = None
    return result


def photograph_frac(photographed: np.ndarray, total: np.ndarray) -> float:
    denominator = int(total.sum())
    if denominator == 0:
        return np.nan
    return float((photographed & total).sum() / denominator)


def psnr_ssim(reference: np.ndarray, candidate: np.ndarray, mask: np.ndarray | None = None):
    if mask is not None:
        ref = reference[mask]
        cand = candidate[mask]
    else:
        ref = reference.reshape(-1, 3)
        cand = candidate.reshape(-1, 3)
    if not len(ref):
        return {"psnr": np.nan, "ssim": np.nan}
    mse = float(np.mean((ref - cand) ** 2))
    psnr = float("inf") if mse == 0 else float(10.0 * np.log10((255.0 ** 2) / mse))
    ssim = _ssim(reference, candidate, mask)
    return {"psnr": psnr, "ssim": ssim}


def _ssim(a: np.ndarray, b: np.ndarray, mask: np.ndarray | None = None, window=7):
    from scipy.ndimage import uniform_filter

    a = a / 255.0
    b = b / 255.0
    channels = []
    for channel in range(3):
        ac, bc = a[..., channel], b[..., channel]
        mu_a = uniform_filter(ac, window)
        mu_b = uniform_filter(bc, window)
        sigma_a = uniform_filter(ac * ac, window) - mu_a * mu_a
        sigma_b = uniform_filter(bc * bc, window) - mu_b * mu_b
        sigma_ab = uniform_filter(ac * bc, window) - mu_a * mu_b
        c1, c2 = 0.01 ** 2, 0.03 ** 2
        ssim_map = ((2 * mu_a * mu_b + c1) * (2 * sigma_ab + c2)) / ((mu_a ** 2 + mu_b ** 2 + c1) * (sigma_a + sigma_b + c2))
        if mask is not None:
            channels.append(float(ssim_map[mask].mean()) if mask.any() else np.nan)
        else:
            channels.append(float(ssim_map.mean()))
    return float(np.nanmean(channels))


def edge_width_profiles(reference: np.ndarray, candidate: np.ndarray, mask: np.ndarray | None = None,
                        edge_pairs_path: Path | None = None):
    """Frozen 10-90% edge profiles where both images contain a strong frozen edge.

    Edges are frozen from the reference gradient (horizontal scan runs).
    """
    pairs = []
    if edge_pairs_path is not None and edge_pairs_path.is_file():
        pairs = json.loads(edge_pairs_path.read_text())
    if not pairs:
        pairs = freeze_edge_pairs(reference, mask)
        if edge_pairs_path is not None:
            edge_pairs_path.write_text(json.dumps(pairs))
    rows = 10
    widths = {"reference": [], "candidate": [], "added": []}
    for pair in pairs[:10]:
        y, x0, x1 = pair["y"], pair["x0"], pair["x1"]
        for label, image in (("reference", reference), ("candidate", candidate)):
            line = image[y, x0:x1 + 1, 0].astype(np.float64)
            if len(line) < 4 or np.ptp(line) < 12.0:
                widths[label].append(np.nan)
                continue
            slope = np.abs(np.diff(line))
            peak = int(np.argmax(slope))
            lo, hi = peak, peak + 1
            low_clip, high_clip = line.min() + 0.1 * np.ptp(line), line.min() + 0.9 * np.ptp(line)
            while lo > 0 and line[lo] > low_clip:
                lo -= 1
            while hi < len(line) - 1 and line[hi] < high_clip:
                hi += 1
            widths[label].append(float(hi - lo))
        if np.isfinite(widths["reference"][-1]) and np.isfinite(widths["candidate"][-1]):
            widths["added"].append(float(widths["candidate"][-1] - widths["reference"][-1]))
    result = {label: {"median": float(np.nanmedian(v)) if v else np.nan} for label, v in widths.items()}
    return result, pairs


def freeze_edge_pairs(reference: np.ndarray, mask: np.ndarray | None, max_pairs: int = 12):
    grey = reference[..., 0]
    gradient = np.abs(np.diff(grey, axis=1))
    usable = np.zeros_like(gradient, dtype=bool)
    usable[..., :] = True
    if mask is not None:
        valid = mask[:, :-1] & mask[:, 1:]
        usable &= valid
    pairs = []
    for y in range(40, gradient.shape[0] - 40, 23):
        row = np.where(usable[y])[0]
        if len(row) < 8:
            continue
        strength = gradient[y, row]
        order = row[np.argsort(-strength)]
        taken = []
        for x in order:
            if all(abs(x - t) > 26 for t in taken):
                taken.append(x)
            if len(taken) >= 2:
                break
        for x in taken:
            x0, x1 = max(0, x - 9), min(gradient.shape[1] - 1, x + 9)
            pairs.append({"y": int(y), "x0": int(x0), "x1": int(x1)})
        if len(pairs) >= max_pairs:
            break
    return pairs


def build_frozen_camera(view: dict) -> RasterCamera:
    """Camera for a frozen-view spec: novel (room_to_camera) or captured
    (scaled projection with square crop)."""
    if "room_to_camera" in view:
        return build_novel_view(view)
    room_to_camera = np.asarray(view["projection"], dtype=np.float64).reshape(4, 4)[:3, :]
    return RasterCamera(view["id"], view["width"], view["height"], np.asarray(room_to_camera),
                        view["fx"], view["fy"], view["cx"], view["cy"])
