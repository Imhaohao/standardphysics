#!/usr/bin/env bash
# Fine-tunes the on-phone detector so it also finds door handles, light switches, outlets, soap and
# paper towel dispensers, toilet paper, hand dryers, mirrors and countertops (and grab bars and signs
# from any extra folders), while keeping the COCO furniture it already finds.
#
#   ios/scripts/train-detector.sh            downloads photos, trains, scores and exports into the work folder
#   ios/scripts/train-detector.sh --install  copies the last run's model into the app and rewrites LICENSES.md
#
# Settings are SP_* environment variables, listed with their defaults in
# scripts/detector/sp_detector/config.py. SP_DETECTOR_WORK_DIR moves the work folder.
set -euo pipefail

ios_dir="$(cd "$(dirname "$0")/.." && pwd)"
tools_dir="$ios_dir/scripts/detector"
work_dir="${SP_DETECTOR_WORK_DIR:-$HOME/sp-detector-training}"
run_dir="$work_dir/run"
models_dir="$ios_dir/Resources/Models"

install_model() {
  local staged="$run_dir/ObjectDetector.mlpackage"
  if [[ ! -d "$staged" ]]; then
    echo "There is no trained model in $run_dir yet. Run ios/scripts/train-detector.sh first." >&2
    exit 1
  fi
  rm -rf "$models_dir/ObjectDetector.mlpackage"
  cp -R "$staged" "$models_dir/ObjectDetector.mlpackage"
  "$work_dir/.venv/bin/python" -I -m sp_detector.licenses "$models_dir/LICENSES.md" --datasets "$run_dir/datasets.json"
  echo "Installed the model from $run_dir. Its validation scores are in $run_dir/metrics.json."
}

case "${1:-}" in
  --install) install_model; exit 0 ;;
  "") ;;
  *) echo "usage: $0 [--install]" >&2; exit 2 ;;
esac

mkdir -p "$work_dir"
cd "$work_dir"

uv venv --quiet --allow-existing --python 3.12 .venv
uv pip install --quiet --python .venv/bin/python --editable "$tools_dir[train]"

export HF_HOME="$work_dir/hf"
export FIFTYONE_DATASET_ZOO_DIR="$work_dir/zoo"
export FIFTYONE_DATABASE_DIR="$work_dir/fiftyone-db"
export FIFTYONE_DO_NOT_TRACK=true
# Runs the few operators Metal lacks on the CPU instead of stopping.
export PYTORCH_ENABLE_MPS_FALLBACK=1

# caffeinate keeps a Mac awake for the night; it is absent elsewhere.
keep_awake=()
if command -v caffeinate >/dev/null; then keep_awake=(caffeinate -ims); fi
${keep_awake[@]+"${keep_awake[@]}"} .venv/bin/python -I -m sp_detector.train "$work_dir" 2>&1 | tee "$work_dir/train.log"
