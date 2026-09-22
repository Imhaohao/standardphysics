"""Train Gaussian splats with Brush and record exactly how the run was made.

Brush is the trainer that produced every splat under runs/moffett/splat-training, but the
command that produced them was never written down, so the only record was an agent
transcript. This script is that record: it passes every parameter explicitly rather than
inheriting a Brush default that may change under us, and writes a provenance sidecar
naming the binary, the dataset and the result.

Brush writes nothing to a pipe - it prints progress only to a terminal - so process.log
holds the command and whatever Brush does emit, which is usually the command alone. The
command is the part that was missing; the progress bar is not recoverable through a pipe.

Defaults below are the ones the existing exports imply, recovered from their PLY headers
and splat counts. Brush's own defaults differ; see each constant.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import compress_moffett_splat

BRUSH = Path("runs/moffett/tools/brush/brush-app-aarch64-apple-darwin/brush_app")

TOTAL_STEPS = 15000
EXPORT_EVERY = 5000

SH_DEGREE = 2
"""Spherical harmonic bands. Every prior export carries 24 f_rest values, which is
degree 2; Brush defaults to 3, which would carry 45 and roughly double the file."""

MAX_SPLATS = 1_800_000
"""Hard ceiling on primitives. Prior runs plateau exactly here (and at 1.2M and 3.0M
elsewhere), so the ceiling, not convergence, is what stopped them growing."""

SCALE_LOSS_WEIGHT = 1e-8
"""Penalty on splat size. Raising it is the lever against needle-shaped splats, which a
walking capture produces because a splat stretched along the view ray costs nothing."""

OPAC_LOSS_WEIGHT = 1e-9
"""Pressure toward transparency. Raising it clears faint airborne floaters, at the cost
of thinning genuinely dim surfaces."""

EVAL_SPLIT_EVERY = 12
"""Hold out every nth frame for evaluation rather than training on all of them."""

SEED = 42

EXPORTED_PLY = re.compile(r"export_(\d+)\.ply")


def sha256_of(path: Path) -> str:
    with path.open("rb") as opened:
        return hashlib.file_digest(opened, "sha256").hexdigest()


def ply_vertex_count(path: Path) -> int:
    """Read the count out of the ASCII header without loading millions of splats."""
    with path.open("rb") as opened:
        header = opened.read(4096)
    match = re.search(rb"element vertex (\d+)", header)
    if match is None:
        raise ValueError(f"no vertex count in PLY header: {path}")
    return int(match.group(1))


def brush_command(dataset: Path, run_dir: Path, args: argparse.Namespace) -> list[str]:
    return [
        str(args.brush.resolve()), str(dataset.resolve()),
        "--total-steps", str(args.total_steps),
        "--seed", str(args.seed),
        "--sh-degree", str(args.sh_degree),
        "--max-splats", str(args.max_splats),
        "--scale-loss-weight", repr(args.scale_loss_weight),
        "--opac-loss-weight", repr(args.opac_loss_weight),
        "--export-every", str(args.export_every),
        "--export-path", str(run_dir.resolve()),
        "--eval-split-every", str(args.eval_split_every),
        "--eval-save-to-disk",
    ]


def run_brush(command: list[str], log_path: Path) -> float:
    """Run the trainer, echoing its output to the terminal and the log at once."""
    started = time.monotonic()
    with log_path.open("w") as log:
        log.write(" ".join(command) + "\n\n")
        log.flush()
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            sys.stdout.write(line)
            log.write(line)
        code = process.wait()
    if code != 0:
        raise RuntimeError(f"brush exited {code}; see {log_path}")
    return time.monotonic() - started


def final_export(run_dir: Path) -> Path:
    """The highest-numbered export, since Brush pads the step to the run's own width."""
    exports = [path for path in run_dir.glob("export_*.ply") if EXPORTED_PLY.fullmatch(path.name)]
    if not exports:
        raise FileNotFoundError(f"brush wrote no export_*.ply into {run_dir}")
    return max(exports, key=lambda path: int(EXPORTED_PLY.fullmatch(path.name).group(1)))


def provenance_of(command: list[str], dataset: Path, export: Path, seconds: float, args: argparse.Namespace) -> dict:
    return {
        "command": command,
        "brush": str(args.brush),
        "brush_sha256": sha256_of(args.brush),
        "dataset": str(dataset),
        "transforms_sha256": sha256_of(dataset / "transforms.json"),
        "parameters": {
            "total_steps": args.total_steps, "seed": args.seed, "sh_degree": args.sh_degree,
            "max_splats": args.max_splats, "scale_loss_weight": args.scale_loss_weight,
            "opac_loss_weight": args.opac_loss_weight, "export_every": args.export_every,
            "eval_split_every": args.eval_split_every,
        },
        "export": str(export),
        "export_splats": ply_vertex_count(export),
        "seconds": round(seconds, 1),
        "note": "Splat count reaching max_splats means the ceiling stopped growth, not convergence",
    }


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Prepared dataset directory holding transforms.json")
    parser.add_argument("run_dir", type=Path, help="New directory to write exports, logs and provenance into")
    parser.add_argument("--brush", type=Path, default=BRUSH)
    parser.add_argument("--total-steps", type=int, default=TOTAL_STEPS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--sh-degree", type=int, default=SH_DEGREE)
    parser.add_argument("--max-splats", type=int, default=MAX_SPLATS)
    parser.add_argument("--scale-loss-weight", type=float, default=SCALE_LOSS_WEIGHT)
    parser.add_argument("--opac-loss-weight", type=float, default=OPAC_LOSS_WEIGHT)
    parser.add_argument("--export-every", type=int, default=EXPORT_EVERY)
    parser.add_argument("--eval-split-every", type=int, default=EVAL_SPLIT_EVERY)
    parser.add_argument("--skip-spz", action="store_true", help="Stop at the PLY instead of compressing it")
    args = parser.parse_args(argv)
    if not args.brush.is_file():
        parser.error(f"no brush binary at {args.brush}")
    if not (args.dataset / "transforms.json").is_file():
        parser.error(f"no transforms.json in {args.dataset}")
    if args.run_dir.exists():
        parser.error("choose a new run directory to preserve run provenance")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse(argv)
    args.run_dir.mkdir(parents=True)
    command = brush_command(args.dataset, args.run_dir, args)
    seconds = run_brush(command, args.run_dir / "process.log")
    export = final_export(args.run_dir)
    report = provenance_of(command, args.dataset, export, seconds, args)
    (args.run_dir / "run.provenance.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"{report['export_splats']:,} splats in {seconds:.0f}s -> {export}")
    if not args.skip_spz:
        compress_moffett_splat.main([str(export), str(export.with_suffix(".spz"))])


if __name__ == "__main__":
    main()
