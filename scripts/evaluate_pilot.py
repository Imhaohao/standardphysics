"""Evaluate render-efficiency held-out views with the frozen metric code.

Reads rendered PNGs produced by the trainer, their source photographs, and the
frozen static masks, then writes per-view PSNR/SSIM and means to a JSON.  The
metric values come from ``render_efficiency.metrics``, never from the language
model's summary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from standardphysics_pipeline.render_efficiency import psnr, ssim


def _load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as opened:
        return np.asarray(opened.convert("RGB"), dtype=np.float64) / 255.0


def _load_static_mask(path: Path) -> np.ndarray:
    with Image.open(path) as opened:
        grey = np.asarray(opened.convert("L"))
    return grey > 250


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("renders", type=Path, help="directory of rendered PNGs named image-*.png")
    parser.add_argument("dataset", type=Path, help="pilot dataset with images/ and masks/")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    renders = sorted(args.renders.glob("image-*.png"))
    if not renders:
        raise SystemExit(f"no image-*.png in {args.renders}")

    views = []
    for render in renders:
        name = render.stem
        original = args.dataset / "images" / f"{name}.jpg"
        mask = args.dataset / "masks" / f"{name}.png"
        if not original.is_file():
            raise SystemExit(f"missing original for {name}")
        if not mask.is_file():
            raise SystemExit(f"missing mask for {name}")
        reference = _load_rgb(original)
        candidate = _load_rgb(render)
        static = _load_static_mask(mask)
        views.append({
            "frame": name,
            "full_psnr": psnr(reference, candidate),
            "masked_psnr": psnr(reference, candidate, static),
            "masked_ssim": ssim(reference, candidate, static),
        })

    full_mean = float(np.mean([v["full_psnr"] for v in views]))
    masked_mean = float(np.mean([v["masked_psnr"] for v in views]))
    ssim_mean = float(np.mean([v["masked_ssim"] for v in views]))
    worst_masked = min(v["masked_psnr"] for v in views)

    result = {
        "renders_dir": str(args.renders),
        "view_count": len(views),
        "mean_full_psnr_db": full_mean,
        "mean_masked_psnr_db": masked_mean,
        "mean_masked_ssim": ssim_mean,
        "worst_masked_psnr_db": float(worst_masked),
        "metric": "decoded sRGB float64 [0,1]; static-region mask = L>250; SSIM gaussian 11x11 sigma 1.5",
        "views": views,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("view_count", "mean_full_psnr_db", "mean_masked_psnr_db", "mean_masked_ssim", "worst_masked_psnr_db")}, indent=2))


if __name__ == "__main__":
    main()
