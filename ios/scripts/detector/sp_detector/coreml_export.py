"""Converts a D-FINE detector to the Core ML package the app bundles.

The package returns, per query, its best sigmoid score, that class id, and a box (cx, cy, w, h)
normalized to the stretched 640x640 input. DETR-style output needs no NMS; Swift thresholds it.
The class names go into the `labels` metadata entry, which the app reads to name class ids.

`python -m sp_detector.coreml_export STAGED_PATH` converts the published COCO weights; training
calls `export` with its fine-tuned model.
"""

import argparse
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

import coremltools as ct
import numpy as np
import torch
from PIL import Image
from transformers import DFineForObjectDetection
from transformers.models.d_fine import modeling_d_fine

from sp_detector import base_model

# Anchors outside the image are marked with float32 max upstream, which overflows FP16.
FP16_SAFE_INVALID_ANCHOR = 1e4
AUTHOR = f"Peng et al., D-FINE (github.com/Peterande/D-FINE); weights {base_model.SOURCE_URL}"


@dataclass(frozen=True)
class ExportDescription:
    summary: str
    source: str
    revision: str


PUBLISHED_COCO = ExportDescription(
    summary=(
        "D-FINE nano object detector trained on COCO. Per query: best sigmoid score, its COCO class id, "
        "and box (cx, cy, w, h) normalized to the input."
    ),
    source=base_model.SOURCE_URL,
    revision=base_model.REVISION,
)


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


def load_for_export(model_source: str, revision: str | None) -> DFineForObjectDetection:
    """A fixed anchor_image_size makes the anchors constants instead of traced in-place writes."""
    modeling_d_fine.DFineIntegral.forward = integral_with_matmul
    model = DFineForObjectDetection.from_pretrained(
        model_source, revision=revision, anchor_image_size=[base_model.INPUT_SIZE, base_model.INPUT_SIZE]
    ).eval()
    core = model.model
    core.anchors = torch.where(core.valid_mask, core.anchors, torch.tensor(FP16_SAFE_INVALID_ANCHOR))
    return model


def labels_in_class_order(model: DFineForObjectDetection) -> list[str]:
    id2label = model.config.id2label
    return [id2label[index] for index in range(len(id2label))]


def convert(model: DFineForObjectDetection, description: ExportDescription) -> ct.models.MLModel:
    example = torch.rand(1, 3, base_model.INPUT_SIZE, base_model.INPUT_SIZE)
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
    mlmodel.short_description = description.summary
    mlmodel.license = "Apache-2.0"
    mlmodel.author = AUTHOR
    mlmodel.user_defined_metadata["source"] = description.source
    mlmodel.user_defined_metadata["revision"] = description.revision
    mlmodel.user_defined_metadata["labels"] = ",".join(labels_in_class_order(model))
    return mlmodel


def probe(mlmodel: ct.models.MLModel) -> None:
    """Core ML can only run a model on macOS; elsewhere the package is saved untested."""
    if platform.system() != "Darwin":
        print("Skipping the Core ML probe: Core ML predictions only run on macOS")
        return
    gray = Image.new("RGB", (base_model.INPUT_SIZE, base_model.INPUT_SIZE), (128, 128, 128))
    outputs = mlmodel.predict({"image": gray})
    print({name: np.asarray(value).shape for name, value in outputs.items()})


def export(model_source: str, revision: str | None, description: ExportDescription, staged: Path) -> None:
    mlmodel = convert(load_for_export(model_source, revision), description)
    shutil.rmtree(staged, ignore_errors=True)
    mlmodel.save(str(staged))
    probe(mlmodel)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert the published D-FINE COCO weights to Core ML.")
    parser.add_argument("staged", type=Path, help="where to write the .mlpackage")
    export(base_model.REPO, base_model.REVISION, PUBLISHED_COCO, parser.parse_args().staged)


if __name__ == "__main__":
    main()
