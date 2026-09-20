"""Produce a reproducible Moffett pilot split for the render-efficiency benchmark.

Sorts frames by ARKit trajectory order (``pose_index``) and selects held-out
views at separated strides so validation and test frames are not adjacent video
frames of the training set.  This is a deterministic, reproducible starting
split: near-duplicate grouping and a real visual review of independence are
recorded as still-required, not claimed.

The policy target is 32 training / 8 validation / 8 final-test views; the JSON
records the achieved counts plus why they may be fewer, and never fabricates
independence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def _sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared", type=Path, default=Path("runs/moffett/splat-datasets/center"))
    parser.add_argument("output", type=Path, default=Path("runs/moffett/render-efficiency/r001/pilot-manifest.json"))
    parser.add_argument("--train", type=int, default=32)
    parser.add_argument("--validation", type=int, default=8)
    parser.add_argument("--test", type=int, default=8)
    parser.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args()

    transforms = json.loads((args.prepared / "transforms.json").read_text())
    provenance = json.loads((args.prepared / "provenance.json").read_text())
    frames = transforms["frames"]
    by_file = {entry["filename"]: entry for entry in provenance["frames"]}
    if len(frames) != len(by_file):
        raise SystemExit("transforms.json and provenance.json frame counts disagree")

    ordered = sorted(frames, key=lambda f: by_file[f["file_path"].split("/")[-1]]["pose_index"])
    test_stride = max(1, len(ordered) // args.test)

    test_indices = set(np.arange(0, len(ordered), test_stride)[: args.test])
    remaining = [i for i in range(len(ordered)) if i not in test_indices]
    validation_indices = set(remaining[:: max(1, len(remaining) // args.validation)][: args.validation])
    reserved = test_indices | validation_indices
    available = [i for i in range(len(ordered)) if i not in reserved]
    train_indices = set(available[: args.train])

    if not (train_indices and validation_indices and test_indices):
        raise SystemExit("split produced an empty group; not enough separated frames")
    if train_indices & validation_indices or train_indices & test_indices or validation_indices & test_indices:
        raise SystemExit("split groups are not disjoint")

    def pick(indices):
        return [{"file_path": ordered[i]["file_path"], "mask_path": ordered[i]["mask_path"]} for i in sorted(indices)]

    manifest = {
        "policy": "docs/deepseek-lidar-experiment-policy.json",
        "seed": args.seed,
        "split_unit": "ARKit pose_index trajectory order",
        "split_independence_reviewed": False,
        "split_independence_note": (
            "deterministic stride over trajectory order; near-duplicate grouping and a real "
            "visual review of trajectory separation remain to be done before Gate 1"
        ),
        "targets": {"train": args.train, "validation": args.validation, "test": args.test},
        "achieved": {
            "train": len(train_indices),
            "validation": len(validation_indices),
            "test": len(test_indices),
        },
        "splits": {
            "train": pick(train_indices),
            "validation": pick(validation_indices),
            "test": pick(test_indices),
        },
        "input_hashes": {
            "transforms_sha256": _sha256(args.prepared / "transforms.json"),
            "provenance_sha256": _sha256(args.prepared / "provenance.json"),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"achieved": manifest["achieved"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
