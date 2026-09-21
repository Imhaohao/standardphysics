"""Repair the Brush/SplatX split so both trainers optimise identical train IDs.

The b0-v2-r1 Brush run passed ``--eval-split-every 5`` over a 40-frame
transforms.json, which held out every fifth frame in trajectory order
(038,083,088,186,210,226,241,296) instead of the manifest validation set
(144,149,166,177,182,186,190,195). Only 186 overlapped, so the existing
21.9253 dB / 0.69126 SSIM does not rank a backend and must not be used.

This script builds a Brush-format training dataset that contains exactly the
manifest train frames (the same 32 IDs SplatX trained on), leaves validation
out of transforms.json entirely, and then verifies the loaded IDs across all
three records: SplatX COLMAP images.txt, the frozen provenance, and the new
Brush dataset. It asserts IDs, not just 32/8 counts.

It never reads the 8 final-test RGBs. It does not rebuild SplatX or Brush; it
only shapes the input the existing binaries already accept.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPLATX_EVAL = ROOT / "runs/moffett/splatx-evaluation"
PROVENANCE = SPLATX_EVAL / "pilot-colmap/provenance.json"
COLMAP = SPLATX_EVAL / "pilot-colmap"
BRUSH_SOURCE = ROOT / "runs/moffett/render-efficiency/r001/pilot-dataset-v2"
BRUSH = ROOT / "runs/moffett/tools/brush/brush-app-aarch64-apple-darwin/brush_app"
OUT = SPLATX_EVAL / "pilot-brush"
OUT_TRAIN = OUT / "train"


def _every_nth(names: list[str], n: int) -> list[str]:
    return names[::n]


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    try:
        os.link(source, target)
    except OSError:
        import shutil
        shutil.copyfile(source, target)


def _splatx_colmap_names(split: str) -> list[str]:
    lines = (COLMAP / split / "sparse/0/images.txt").read_text().splitlines()
    return [line.split()[-1] for line in lines if line.strip() and not line.startswith("#")]


def _frame_ids(entries: list[dict]) -> list[str]:
    return [Path(e["file_path"]).name for e in entries]


def build() -> None:
    prov = json.loads(PROVENANCE.read_text())
    train_ids = _frame_ids(prov["splits"]["train"])
    val_ids = _frame_ids(prov["splits"]["validation"])
    assert len(train_ids) == 32 and len(val_ids) == 8, "unexpected split sizes"
    assert len(set(train_ids)) == 32 and len(set(val_ids)) == 8, "duplicate IDs in split"
    assert not set(train_ids) & set(val_ids), "train/validation overlap"

    transforms = json.loads((BRUSH_SOURCE / "transforms.json").read_text())
    by_name = {Path(f["file_path"]).name: f for f in transforms["frames"]}

    val_frames, train_frames = [], []
    for name in train_ids:
        train_frames.append(by_name[name])
    for name in val_ids:
        val_frames.append(by_name[name])

    if OUT_TRAIN.exists():
        raise FileExistsError(f"choose a new output; {OUT_TRAIN} exists")
    (OUT_TRAIN / "images").mkdir(parents=True)
    (OUT_TRAIN / "masks").mkdir(parents=True)
    for frame in train_frames:
        for key in ("file_path", "mask_path"):
            source = BRUSH_SOURCE / frame[key]
            _link(source, OUT_TRAIN / frame[key])

    seed_rel = transforms["ply_file_path"]
    _link(BRUSH_SOURCE / seed_rel, OUT_TRAIN / seed_rel)

    (OUT_TRAIN / "transforms.json").write_text(json.dumps({
        "camera_model": transforms["camera_model"],
        "ply_file_path": seed_rel,
        "frames": train_frames,
    }, indent=2) + "\n")
    (OUT_TRAIN / "validation-frames.json").write_text(json.dumps({
        "camera_model": transforms["camera_model"],
        "frames": val_frames,
        "note": "held-out validation; never part of training",
    }, indent=2) + "\n")
    (OUT_TRAIN / "brush-split.provenance.json").write_text(json.dumps({
        "source_of_truth": str(PROVENANCE),
        "train_ids": train_ids,
        "validation_ids": val_ids,
        "train_count": len(train_ids),
        "validation_count": len(val_ids),
        "brush_source_transforms_sha256": digest(BRUSH_SOURCE / "transforms.json"),
        "seed_sha256": digest(OUT_TRAIN / seed_rel),
        "note": "validation excluded from transforms.json; --eval-split-every must be omitted",
    }, indent=2) + "\n")
    print(json.dumps({"train": len(train_ids), "validation": len(val_ids),
                      "output": str(OUT_TRAIN)}, indent=2))


def verify() -> None:
    prov = json.loads(PROVENANCE.read_text())
    manifest_train = _frame_ids(prov["splits"]["train"])
    manifest_val = _frame_ids(prov["splits"]["validation"])

    colmap_train = _splatx_colmap_names("train")
    colmap_val = _splatx_colmap_names("validation")

    brush_train = _frame_ids(json.loads((OUT_TRAIN / "transforms.json").read_text())["frames"])

    # Byte-level parity: each loaded RGB and mask must hash to its source.
    source_transforms = json.loads((BRUSH_SOURCE / "transforms.json").read_text())
    source_by_name = {Path(f["file_path"]).name: f for f in source_transforms["frames"]}
    rgb_ok, mask_ok = True, True
    for name in manifest_train:
        rgb_ok &= digest(OUT_TRAIN / "images" / name) == digest(BRUSH_SOURCE / "images" / name)
        mask_name = Path(source_by_name[name]["mask_path"]).name
        mask_ok &= digest(OUT_TRAIN / "masks" / mask_name) == digest(BRUSH_SOURCE / "masks" / mask_name)

    log = (SPLATX_EVAL / "pilot-3000.log").read_text()
    first = next(line for line in log.splitlines() if "splatx train:" in line)
    n_cameras = int(first.split("cameras")[0].strip().split()[-1])

    checks = {
        "manifest_train_is_32": len(manifest_train) == 32,
        "manifest_validation_is_8": len(manifest_val) == 8,
        "colmap_train_equals_manifest_train": sorted(colmap_train) == sorted(manifest_train),
        "colmap_validation_equals_manifest_validation": sorted(colmap_val) == sorted(manifest_val),
        "brush_train_equals_manifest_train": sorted(brush_train) == sorted(manifest_train),
        "brush_excludes_validation": not set(brush_train) & set(manifest_val),
        "splatx_log_loaded_32_cameras": n_cameras == 32,
        "validation_in_sidecar": sorted(_frame_ids(
            json.loads((OUT_TRAIN / "validation-frames.json").read_text())["frames"])) == sorted(manifest_val),
        "brush_rgb_hashes_match_source": rgb_ok,
        "brush_mask_hashes_match_source": mask_ok,
    }
    report = {
        "checks": checks,
        "manifest_train": manifest_train,
        "manifest_validation": manifest_val,
        "colmap_train": colmap_train,
        "colmap_validation": colmap_val,
        "brush_train": brush_train,
        "splatx_log_cameras": n_cameras,
    }
    print(json.dumps(report, indent=2))
    if not all(checks.values()):
        raise SystemExit(f"split parity FAILED: {[k for k, v in checks.items() if not v]}")
    print("split parity OK: identical 32 train IDs on both trainers; validation excluded")


def verify_brush_load() -> None:
    """Run the black-box Brush trainer and prove it loads exactly the 32 train IDs.

    Brush is silent on a pipe, so the only observable record of what it loaded is
    the names of the eval images it writes with ``--eval-save-to-disk``. We run one
    throwaway step with ``--eval-split-every 2`` (every second frame becomes eval)
    and assert the saved eval names are exactly the every-2nd frame of our train
    order, no validation IDs among them.
    """
    prov = json.loads(PROVENANCE.read_text())
    train_ids = _frame_ids(prov["splits"]["train"])
    val_ids = _frame_ids(prov["splits"]["validation"])
    expected_eval = [Path(n).stem for n in _every_nth(train_ids, 2)]

    with tempfile.TemporaryDirectory() as tmp:
        export = Path(tmp) / "out"
        command = [
            str(BRUSH), str(OUT_TRAIN),
            "--total-steps", "1", "--eval-split-every", "2", "--eval-every", "1",
            "--eval-save-to-disk", "--max-resolution", "64", "--max-splats", "1000",
            "--subsample-points", "8", "--seed", "42", "--export-path", str(export),
        ]
        run = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if run.returncode != 0:
            raise SystemExit(f"brush diagnostic failed: {run.stdout}\n{run.stderr}")
        loaded_eval = sorted(p.stem for p in (export / "eval_1").glob("image-*.png"))
        report = {
            "expected_eval_every_2nd": expected_eval,
            "brush_saved_eval_names": loaded_eval,
            "brush_eval_matches_train_order": loaded_eval == sorted(expected_eval),
            "brush_eval_excludes_validation": not set(loaded_eval) & set(val_ids),
        }
        print(json.dumps(report, indent=2))
        if not report["brush_eval_matches_train_order"] or not report["brush_eval_excludes_validation"]:
            raise SystemExit("brush trainer-loaded IDs do not match the corrected train split")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "verify", "verify-brush"])
    args = parser.parse_args()
    if args.action == "build":
        build()
    elif args.action == "verify":
        verify()
    else:
        verify_brush_load()


if __name__ == "__main__":
    main()
