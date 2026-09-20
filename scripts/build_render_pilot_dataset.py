"""Build the frozen Moffett render-efficiency pilot dataset for Brush.

Reads the prepared center dataset (1920px), applies the frozen pilot split, and
writes a new, smaller dataset at the policy's 1280px maximum edge.  Intrinsics
are rescaled with the half-pixel correction the camera owner already uses;
poses are resolution-independent and copied unchanged.  The LiDAR seed cloud is
reused unchanged (metric scene coordinates, independent of image resolution).

The 8 final-test frames are written to a sidecar, never into the training
transforms, so they stay out of any Brush optimisation.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from PIL import Image


def _resized_entry(entry: dict, scale: float) -> dict:
    out = dict(entry)
    out["fl_x"] = entry["fl_x"] * scale
    out["fl_y"] = entry["fl_y"] * scale
    out["cx"] = (entry["cx"] + 0.5) * scale - 0.5
    out["cy"] = (entry["cy"] + 0.5) * scale - 0.5
    out["w"] = round(entry["w"] * scale)
    out["h"] = round(entry["h"] * scale)
    return out


def _resize_image(source: Path, target: Path, size: tuple[int, int]) -> None:
    with Image.open(source) as opened:
        opened.convert("RGB").resize(size, Image.Resampling.LANCZOS).save(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("runs/moffett/splat-datasets/center"))
    parser.add_argument("--manifest", type=Path, default=Path("runs/moffett/render-efficiency/r001/pilot-manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("runs/moffett/render-efficiency/r001/pilot-dataset"))
    parser.add_argument("--max-edge", type=int, default=1280)
    args = parser.parse_args()

    transforms = json.loads((args.source / "transforms.json").read_text())
    by_file = {frame["file_path"]: frame for frame in transforms["frames"]}
    width, height = transforms["frames"][0]["w"], transforms["frames"][0]["h"]
    scale = args.max_edge / max(width, height)
    target_size = (round(width * scale), round(height * scale))

    split = json.loads(args.manifest.read_text())["splits"]
    train_val = split["train"] + split["validation"]
    test = split["test"]

    out = args.output
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "masks").mkdir(parents=True, exist_ok=True)

    def prepare(files):
        names = []
        for item in files:
            rel = item["file_path"]
            frame = by_file[rel]
            assert item["mask_path"], rel
            name = Path(rel).name
            mask_name = Path(item["mask_path"]).name
            _resize_image(args.source / rel, out / "images" / name, target_size)
            _resize_image(args.source / item["mask_path"], out / "masks" / mask_name, target_size)
            entry = _resized_entry(frame, scale)
            entry["file_path"] = f"images/{name}"
            entry["mask_path"] = f"masks/{mask_name}"
            names.append(entry)
        return names

    train_val_frames = prepare(train_val)
    test_frames = prepare(test)

    seed_source = args.source / transforms["ply_file_path"]
    seed_target = out / transforms["ply_file_path"]
    if not seed_target.exists():
        os.link(seed_source, seed_target)

    (out / "transforms.json").write_text(json.dumps({
        "camera_model": transforms["camera_model"],
        "ply_file_path": transforms["ply_file_path"],
        "frames": train_val_frames,
    }, indent=2) + "\n")
    (out / "test-frames.json").write_text(json.dumps({
        "camera_model": transforms["camera_model"],
        "frames": test_frames,
        "note": "held-out final test; never part of training or validation",
    }, indent=2) + "\n")
    (out / "pilot.provenance.json").write_text(json.dumps({
        "source_dataset": str(args.source.resolve()),
        "source_transforms_sha256": _sha256(args.source / "transforms.json"),
        "max_edge_px": args.max_edge,
        "resized_size": list(target_size),
        "scale_factor": scale,
        "train_val_count": len(train_val_frames),
        "test_count": len(test_frames),
        "seed_ply_source": transforms["ply_file_path"],
    }, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"train_val": len(train_val_frames), "test": len(test_frames), "size": list(target_size)}, indent=2))


def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


if __name__ == "__main__":
    main()
