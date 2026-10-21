#!/usr/bin/env bash
# Converts the published D-FINE nano COCO detector (Apache-2.0, see Resources/Models/LICENSES.md) to Core ML
# and bundles it. The conversion lives in scripts/detector/sp_detector/coreml_export.py, which
# train-detector.sh uses for its fine-tuned model too.
set -euo pipefail

ios_dir="$(cd "$(dirname "$0")/.." && pwd)"
tools_dir="$ios_dir/scripts/detector"
work_dir="${SP_DETECTOR_WORK_DIR:-${TMPDIR:-/tmp}/sp-detector-export}"
models_dir="$ios_dir/Resources/Models"
output="$models_dir/ObjectDetector.mlpackage"

mkdir -p "$work_dir" "$models_dir"
cd "$work_dir"

uv venv --quiet --allow-existing --python 3.12 .venv
uv pip install --quiet --python .venv/bin/python --editable "$tools_dir"

HF_HOME="$work_dir/hf" .venv/bin/python -I -m sp_detector.coreml_export "$work_dir/ObjectDetector.mlpackage"

rm -rf "$output"
mv "$work_dir/ObjectDetector.mlpackage" "$output"
.venv/bin/python -I -m sp_detector.licenses "$models_dir/LICENSES.md"
du -sh "$output"
