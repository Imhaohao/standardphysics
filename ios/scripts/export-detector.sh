#!/usr/bin/env bash
# Exports the COCO object detector to Core ML for the live overlay.
# Ultralytics weights are AGPL-3.0: the output is gitignored and must not be committed.
set -euo pipefail

ios_dir="$(cd "$(dirname "$0")/.." && pwd)"
work_dir="${SP_DETECTOR_WORK_DIR:-$ios_dir/build/detector-export}"
output="$ios_dir/Resources/Models/ObjectDetector.mlpackage"

mkdir -p "$work_dir" "$(dirname "$output")"
cd "$work_dir"

uv venv --quiet --allow-existing --python 3.12 .venv
uv pip install --quiet --python .venv/bin/python "ultralytics>=8.4" "coremltools>=8.3" "numpy<=2.3.5" "torch>=2.4,<2.8" "torchvision<0.23"

.venv/bin/python - "$work_dir" <<'PY'
import shutil
import sys
from pathlib import Path

from ultralytics import YOLO

work_dir = Path(sys.argv[1])
exported = None
for weights in ("yolo26n.pt", "yolo11n.pt"):
    try:
        exported = YOLO(weights).export(format="coreml", nms=True, imgsz=640, half=True)
        print(f"exported {weights}")
        break
    except Exception as error:
        print(f"{weights} failed: {error}", file=sys.stderr)
if exported is None:
    sys.exit("no detector could be exported")
staged = work_dir / "ObjectDetector.mlpackage"
shutil.rmtree(staged, ignore_errors=True)
shutil.move(exported, staged)
PY

rm -rf "$output"
mv "$work_dir/ObjectDetector.mlpackage" "$output"
du -sh "$output"
