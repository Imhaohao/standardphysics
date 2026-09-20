"""Run one controlled SplatX-vs-Brush pilot on the corrected split.

Both trainers optimise the identical explicit 32 train IDs (built and verified by
``repair_split_parity.py``); validation is excluded from both and rendered only
through the common SplatX native renderer. Settings that both backends share are
matched; settings that differ are recorded, not silently equated.

The existing 3,000-step SplatX export (pilot-3000.ply) and its validation
renders are reused. Only the corrected Brush run is produced here.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "runs/moffett/splatx-evaluation"
UP = EVAL / "upstream"
BRUSH = ROOT / "runs/moffett/tools/brush/brush-app-aarch64-apple-darwin/brush_app"
TRAIN = EVAL / "pilot-brush/train"
DATASET = ROOT / "runs/moffett/render-efficiency/r001/pilot-dataset-v2"
PROV = json.loads((EVAL / "pilot-colmap/provenance.json").read_text())
OUT = EVAL / "brush-control"

MATCHED = {
    "total_steps": 3000, "seed": 42, "sh_degree": 2, "ssim_weight": 0.2,
    "max_splats": 1_000_000, "resolution": "1280x960", "train_ids": 32,
    "init_points": 303342, "masks": "none (neither backend applied person masks)",
    "eval_split": "none (validation excluded from transforms.json)",
}
DIFFERS = {
    "densification": "SplatX MCMC (cap 1M) vs Brush refine/growth (refine-every 200, growth-grad-threshold 4e-5, growth-stop-iter 15000)",
    "learning_rates": "SplatX scene-scale LR vs Brush fixed per-param LR defaults",
    "regularization": "SplatX built-in opacity/scale regularization vs Brush scale-loss 1e-8 / opac-loss 1e-9",
    "rasterizer": "SplatX resident Metal classic rasterization vs Brush WebGPU/Metal backend",
    "aux_loss_time": "Brush --aux-loss-time 0.9; SplatX has no analogue",
    "nondeterminism": "both seed 42 but GPU atomic accumulation is not bitwise deterministic",
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ply_vertex_count(path: Path) -> int:
    with path.open("rb") as opened:
        header = opened.read(4096)
    match = re.search(rb"element vertex (\d+)", header)
    if match is None:
        raise ValueError(f"no vertex count in PLY header: {path}")
    return int(match.group(1))


def run_brush() -> Path:
    out = OUT / "train"
    out.mkdir(parents=True)
    command = [
        str(BRUSH), str(TRAIN),
        "--total-steps", str(MATCHED["total_steps"]),
        "--seed", str(MATCHED["seed"]),
        "--sh-degree", str(MATCHED["sh_degree"]),
        "--ssim-weight", repr(MATCHED["ssim_weight"]),
        "--max-splats", str(MATCHED["max_splats"]),
        "--export-every", str(MATCHED["total_steps"]),
        "--export-path", str(out),
    ]
    started = time.monotonic()
    with (out / "process.log").open("w") as log:
        log.write(" ".join(command) + "\n\n")
        log.flush()
        run = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in run.stdout:
            log.write(line)
        code = run.wait()
    if code != 0:
        raise RuntimeError(f"brush exited {code}; see {out/'process.log'}")
    ply = out / "export_3000.ply"
    if not ply.is_file():
        raise FileNotFoundError(f"brush wrote no {ply}")
    (out / "train.provenance.json").write_text(json.dumps({
        "command": command, "brush_sha256": sha256_of(BRUSH),
        "train_dataset": str(TRAIN), "wall_seconds": round(time.monotonic() - started, 1),
        "export_splats": ply_vertex_count(ply),
        "matched": MATCHED, "differs": DIFFERS,
    }, indent=2) + "\n")
    return ply


def render_validation(ply: Path) -> None:
    out = OUT / "validation"
    out.mkdir(parents=True, exist_ok=False)
    records = []
    for view in PROV["splits"]["validation"]:
        target = out / (Path(view["file_path"]).stem + ".png")
        command = [
            str(UP / ".build/release/splatx"), "render", "--ply", str(ply),
            "--data", str(EVAL / "pilot-colmap/validation"), "--factor", "1",
            "--cam", str(view["cam_index"]), "--out", str(target),
            "--metallib", str(UP / "build/splatx.metallib"),
        ]
        started = time.monotonic()
        run = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if run.returncode != 0:
            raise RuntimeError(f"splatx render failed: {run.stdout}\n{run.stderr}")
        target.with_suffix(".log").write_text(run.stdout + run.stderr)
        records.append({"source": view["file_path"], "camera": view["cam_index"],
                        "wall_seconds": round(time.monotonic() - started, 2),
                        "sha256": sha256_of(target)})
    (out / "render-provenance.json").write_text(json.dumps({
        "ply": str(ply), "ply_sha256": sha256_of(ply), "renders": records,
    }, indent=2) + "\n")


def evaluate() -> None:
    out = OUT / "brush-metrics.json"
    command = [str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/evaluate_pilot.py"),
               str(OUT / "validation"), str(DATASET), str(out)]
    run = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if run.returncode != 0:
        raise RuntimeError(run.stdout + run.stderr)
    brush = json.loads(out.read_text())
    splatx = json.loads((EVAL / "validation/splatx-metrics.json").read_text())
    summary = {
        "purpose": "controlled common-heldout comparison after split repair; matched budget/resolution/SH/seed/init",
        "not_equivalent": "settings listed under differs prevent an equal-budget equivalence claim",
        "matched": MATCHED, "differs": DIFFERS,
        "brush_export_splats": ply_vertex_count(OUT / "train/export_3000.ply"),
        "splatx_export_splats": json.loads(
            (EVAL / "status.json").read_text())["pilot_measurements"]["exported_splats"],
        "brush_masked_psnr_db": brush["mean_masked_psnr_db"],
        "brush_masked_ssim": brush["mean_masked_ssim"],
        "splatx_masked_psnr_db": splatx["mean_masked_psnr_db"],
        "splatx_masked_ssim": splatx["mean_masked_ssim"],
        "brush_views": brush["views"], "splatx_views": splatx["views"],
    }
    (OUT / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({
        "brush_masked_psnr_db": brush["mean_masked_psnr_db"],
        "brush_masked_ssim": brush["mean_masked_ssim"],
        "splatx_masked_psnr_db": splatx["mean_masked_psnr_db"],
        "splatx_masked_ssim": splatx["mean_masked_ssim"],
    }, indent=2))


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"choose a new output; {OUT} exists")
    OUT.mkdir(parents=True)
    ply = run_brush()
    render_validation(ply)
    evaluate()


if __name__ == "__main__":
    main()
