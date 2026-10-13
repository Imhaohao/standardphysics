"""room-changes BEFORE AFTER --out DIR, and room-changes evaluate DIR TRUTH."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _run(args: argparse.Namespace) -> None:
    from .pipeline import Settings, run

    settings = Settings(frames_per_video=args.frames, namer=args.namer, fov_deg=args.fov,
                        camera_height_m=args.camera_height, rotate_cw=args.rotate,
                        reuse_reconstruction=not args.fresh)
    report = run(args.before, args.after, args.out, settings)
    print()
    print(report["summary"])
    for change in report["changes"]:
        print(f"  {change['id']}  {change['type']:<8} {change['sentence']} ({change['size_text']})")
    print(f"\nWrote {args.out / 'scene.json'}")


def _evaluate(args: argparse.Namespace) -> None:
    from .evaluate import evaluate

    report = evaluate(args.result, args.truth)
    print(json.dumps({key: value for key, value in report.items() if key != "changes"}, indent=1))
    for row in report["changes"]:
        print(f"  {row['type']:<8} {row['truth']:<16} -> {row.get('found') or 'missed'} {row.get('name', '')}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="room-changes", description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="compare two videos of one room")
    run.add_argument("before", type=Path)
    run.add_argument("after", type=Path)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--frames", type=int, default=32, help="frames sampled from each video")
    run.add_argument("--namer", choices=["auto", "qwen", "none"], default="auto")
    run.add_argument("--fov", type=float, help="horizontal field of view of the video in degrees, if known")
    run.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], default=0,
                     help="turn every frame clockwise by this many degrees, for videos that don't say which way is up")
    run.add_argument("--camera-height", type=float,
                     help="how high you held the phone above the floor, in metres; corrects the model's scale")
    run.add_argument("--fresh", action="store_true", help="reconstruct again even if a cached result exists")
    run.set_defaults(handler=_run)
    score = commands.add_parser("evaluate", help="score a result against a rendered room's truth.json")
    score.add_argument("result", type=Path)
    score.add_argument("truth", type=Path)
    score.set_defaults(handler=_evaluate)
    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(sys.argv[1:] if argv is None else argv)
    args.handler(args)


if __name__ == "__main__":
    main()
