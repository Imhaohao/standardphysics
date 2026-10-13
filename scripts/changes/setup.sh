#!/usr/bin/env bash
# Build the environment the change detector's models run in, at packages/changes/.venv.
#
# It is separate from the repository's .venv: MapAnything and the vision models pull in
# torch and transformers, which the API image does not need. The first run of the
# detector also downloads about 15 GB of weights into ~/.cache (MapAnything, its
# DINOv2 backbone, DINOv2-large, Mask2Former COCO panoptic and Qwen3-VL 8B in 4-bit).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV="$ROOT/packages/changes/.venv"
MAPANYTHING="mapanything @ git+https://github.com/facebookresearch/map-anything@f7ebafb4d8349776705aaa686cf928988d1bd7f4"

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }
uv venv --python 3.11 "$ENV"
export VIRTUAL_ENV="$ENV"
uv pip install \
  "torch==2.14.*" torchvision "numpy>=2" scipy "opencv-python-headless>=4.10" pillow \
  "transformers==5.19.0" huggingface_hub safetensors einops natsort orjson python-box requests tqdm \
  hydra-core jaxtyping timm pytest
# mapanything and uniception ask for a second torch and rerun-sdk in their metadata;
# none of the modules used here import them.
uv pip install --no-deps "uniception==0.1.6" "$MAPANYTHING"
if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  uv pip install "mlx-vlm==0.3.9"
fi
uv pip install --no-deps -e "$ROOT/packages/changes"
echo "Ready. Run: $ENV/bin/room-changes run before.mp4 after.mp4 --out out/my-room"
