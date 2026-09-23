"""Machine landmark alignment for the photo-mesh 500 benchmark.

Frozen procedure: Harris corners are detected on the PHOTOGRAPHIC reference
only, greedily spread, then template-matched into the candidate render with
normalized cross-correlation. Every landmark is therefore a visible static
correspondence frozen before comparing candidates; the reported error is the
matched displacement at 500 x 500. This is a machine proxy for the policy's
20-landmark human check, never its replacement.

Output per view: found count, median/p95 error px, per-landmark detail.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from moffett_image_registration import CAPTURES


def harris_corners(grey: np.ndarray, max_points: int = 80):
    import cv2
    corners = cv2.goodFeaturesToTrack(grey, max_points, 0.01, 24)
    if corners is None:
        return []
    picked, used = [], set()
    for x, y in corners[:, 0, :]:
        if any((x - px) ** 2 + (y - py) ** 2 < 32 * 32 for (px, py) in used):
            continue
        if x < 20 or y < 20 or x > grey.shape[1] - 21 or y > grey.shape[0] - 21:
            continue
        picked.append((float(x), float(y)))
        used.add((x, y))
        if len(picked) >= 20:
            break
    return picked


def best_ncc(template: np.ndarray, search: np.ndarray) -> tuple[float, int, int]:
    th, tw = template.shape
    best = -2.0
    best_dy = best_dx = 0
    t = template - template.mean()
    denom_t = np.sqrt((t * t).sum()) or 1.0
    for dy in range(-15, 16):
        for dx in range(-15, 16):
            window = search[dy + 15:dy + 15 + th, dx + 15:dx + 15 + tw]
            w = window.astype(np.float64)
            w = w - w.mean()
            denom = np.sqrt((w * w).sum()) or 1.0
            score = float((t * w).sum() / (denom_t * denom))
            if score > best:
                best, best_dy, best_dx = score, dy, dx
    return best, best_dy, best_dx


def measure_view(reference_grey: np.ndarray, candidate_grey: np.ndarray,
                 verification_grey: np.ndarray | None = None):
    template_half = 10
    landmarks = []
    padded = np.pad(candidate_grey, 26, mode="edge")
    for x, y in harris_corners(reference_grey):
        xi, yi = int(x), int(y)
        template = reference_grey[yi - template_half:yi + template_half + 1, xi - template_half:xi + template_half + 1]
        if verification_grey is not None:
            ver_window = verification_grey[yi - 40:yi + 41, xi - 40:xi + 41]
            if ver_window.shape != (81, 81):
                continue
            static_score, sdy, sdx = best_ncc(template.astype(np.float64), ver_window.astype(np.float64))
            if static_score < 0.75 or abs(sdy) > 4 or abs(sdx) > 4:
                landmarks.append({"position": [x, y], "score": round(static_score, 3),
                                  "static": False, "found": False, "offset_px": None})
                continue
        search = padded[yi + 1:yi + 52, xi + 1:xi + 52]
        score, dy, dx = best_ncc(template.astype(np.float64), search.astype(np.float64))
        offset = float(np.hypot(dy, dx))
        landmarks.append({"position": [x, y], "score": round(score, 3), "offset_px": round(offset, 2),
                          "found": score >= 0.4,
                          "static": verification_grey is None or static_score >= 0.75})
    found = [l for l in landmarks if l["found"]]
    errors = [l["offset_px"] for l in found]
    return {
        "landmark_count": len(landmarks),
        "static_landmarks": int(sum(1 for l in landmarks if l.get("static", True))),
        "found": len(found),
        "median_error_px": float(np.median(errors)) if errors else None,
        "p95_error_px": float(np.percentile(errors, 95)) if errors else None,
        "max_error_px": float(max(errors)) if errors else None,
        "note": "Harris-from-reference template match; static-verified against a neighbouring capture frame when provided",
        "landmarks": landmarks,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    evaluation = json.loads(args.evaluation.read_text())
    run_dir = args.evaluation.parent.parent.parent.parent
    directory = args.evaluation.parent
    splits = json.loads((run_dir / "stageA" / "splits.json").read_text())
    capture = CAPTURES[splits["capture"]]
    capture_dir = Path("datasets/phone/moffett") / capture

    def verification_image(frame_id: str):
        index = int(frame_id.split("-")[1])
        neighbour = f"frame_{index + 2:04d}.jpg"
        path = capture_dir / "frames" / neighbour
        if not path.is_file():
            neighbour = f"frame_{max(0, index - 2):04d}.jpg"
            path = capture_dir / "frames" / neighbour
        if not path.is_file():
            return None
        image = Image.open(path).convert("RGB")
        image = image.crop((240, 0, 240 + 1440, 1440)).resize((500, 500), Image.Resampling.BILINEAR)
        return np.asarray(image.convert("L"))

    results = {"views": [], "summary": {}}
    medians, p95s = [], []
    for view in evaluation["views"]:
        if not view.get("reference"):
            results["views"].append({"id": view["id"], "kind": view["kind"], "note": "novel view: no reference"})
            continue
        reference = np.asarray(Image.open(directory / f"{view['id']}-reference-500.png").convert("L"))
        candidate = np.asarray(Image.open(directory / f"{view['id']}-rgb-500.png").convert("L"))
        verification = verification_image(view["id"]) if view["id"].startswith("frame-") else None
        measured = measure_view(reference, candidate, verification)
        measured["id"] = view["id"]
        results["views"].append(measured)
        if measured["median_error_px"] is not None:
            medians.append(measured["median_error_px"])
            p95s.append(measured["p95_error_px"])
    results["summary"] = {
        "views_with_landmarks": int(sum(1 for v in results["views"] if v.get("found"))),
        "median_of_view_medians_px": float(np.median(medians)) if medians else None,
        "max_view_median_px": float(max(medians)) if medians else None,
        "max_view_p95_px": float(max(p95s)) if p95s else None,
        "static_verification": "landmarks must match a neighbouring captured frame to be counted static",
        "machine_proxy_only": True,
    }
    args.out.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results["summary"], indent=1))


if __name__ == "__main__":
    main()
