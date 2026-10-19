#!/usr/bin/env bash
# Converts the D-FINE nano COCO detector (Apache-2.0, see Resources/Models/LICENSES.md) to Core ML.
# The model returns, per query, its best sigmoid score, that class id, and a box (cx, cy, w, h)
# normalized to the stretched 640x640 input. DETR-style output needs no NMS; Swift thresholds it.
set -euo pipefail

ios_dir="$(cd "$(dirname "$0")/.." && pwd)"
work_dir="${SP_DETECTOR_WORK_DIR:-${TMPDIR:-/tmp}/sp-detector-export}"
output="$ios_dir/Resources/Models/ObjectDetector.mlpackage"
repo="ustc-community/dfine-nano-coco"
revision="066438d3d8f0da137a37b38fdf3368fd4afceced"

mkdir -p "$work_dir" "$(dirname "$output")"
cd "$work_dir"

uv venv --quiet --allow-existing --python 3.12 .venv
uv pip install --quiet --python .venv/bin/python \
  "coremltools==9.0" "torch==2.7.0" "transformers==4.57.1" "safetensors" "pillow" "numpy<2.4"

HF_HOME="$work_dir/hf" .venv/bin/python -I - "$repo" "$revision" "$work_dir/ObjectDetector.mlpackage" <<'PY'
import shutil
import sys
from pathlib import Path

import coremltools as ct
import numpy as np
import torch
from PIL import Image
from transformers import DFineForObjectDetection
from transformers.models.d_fine import modeling_d_fine

repo, revision, staged = sys.argv[1], sys.argv[2], Path(sys.argv[3])
INPUT_SIZE = 640
# Anchors outside the image are marked with float32 max upstream, which overflows FP16.
FP16_SAFE_INVALID_ANCHOR = 1e4


class DecodedDetector(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, image):
        result = self.model(pixel_values=image)
        scores, class_ids = result.logits.sigmoid().max(dim=-1)
        return scores[0], class_ids[0].to(torch.int32), result.pred_boxes[0]


# coremltools only converts F.linear with a 2D weight; the integral layer passes a 1D one.
def integral_with_matmul(self, pred_corners, project):
    batch_size, num_queries, _ = pred_corners.shape
    distribution = torch.softmax(pred_corners.reshape(-1, self.max_num_bins + 1), dim=1)
    return torch.matmul(distribution, project.reshape(-1, 1)).reshape(batch_size, num_queries, -1)


modeling_d_fine.DFineIntegral.forward = integral_with_matmul

# A fixed anchor_image_size makes the anchors constants instead of traced in-place writes.
model = DFineForObjectDetection.from_pretrained(
    repo, revision=revision, anchor_image_size=[INPUT_SIZE, INPUT_SIZE]
).eval()
core = model.model
core.anchors = torch.where(core.valid_mask, core.anchors, torch.tensor(FP16_SAFE_INVALID_ANCHOR))

example = torch.rand(1, 3, INPUT_SIZE, INPUT_SIZE)
with torch.no_grad():
    traced = torch.jit.trace(DecodedDetector(model).eval(), example, strict=False)

mlmodel = ct.convert(
    traced,
    inputs=[ct.ImageType(name="image", shape=example.shape, scale=1 / 255.0, color_layout=ct.colorlayout.RGB)],
    outputs=[
        ct.TensorType(name="scores", dtype=np.float32),
        ct.TensorType(name="classIDs", dtype=np.int32),
        ct.TensorType(name="boxes", dtype=np.float32),
    ],
    convert_to="mlprogram",
    compute_precision=ct.precision.FLOAT16,
    minimum_deployment_target=ct.target.iOS17,
)
labels = [model.config.id2label[index] for index in range(len(model.config.id2label))]
mlmodel.short_description = (
    "D-FINE nano object detector trained on COCO. Per query: best sigmoid score, its COCO class id, "
    "and box (cx, cy, w, h) normalized to the input."
)
mlmodel.license = "Apache-2.0"
mlmodel.author = "Peng et al., D-FINE (github.com/Peterande/D-FINE); weights huggingface.co/" + repo
mlmodel.user_defined_metadata["source"] = f"https://huggingface.co/{repo}"
mlmodel.user_defined_metadata["revision"] = revision
mlmodel.user_defined_metadata["labels"] = ",".join(labels)

shutil.rmtree(staged, ignore_errors=True)
mlmodel.save(str(staged))

probe = mlmodel.predict({"image": Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (128, 128, 128))})
print({name: np.asarray(value).shape for name, value in probe.items()})
PY

rm -rf "$output"
mv "$work_dir/ObjectDetector.mlpackage" "$output"
du -sh "$output"
