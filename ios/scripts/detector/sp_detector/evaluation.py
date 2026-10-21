"""Scores a model on the validation split with the COCO mean average precision (pycocotools).

`map_50_95` averages over IoU thresholds 0.5 to 0.95; `map_50` counts a box as found at IoU 0.5.
A class with no validation boxes has no score (`None`).
"""

import contextlib
import io
from pathlib import Path

import numpy as np
import torch
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

from sp_detector import base_model

DETECTIONS_PER_IMAGE = 100


def _xywh_pixels(center_box: torch.Tensor) -> list[float]:
    center_x, center_y, width, height = (value * base_model.INPUT_SIZE for value in center_box.tolist())
    return [center_x - width / 2, center_y - height / 2, width, height]


def _image_detections(logits: torch.Tensor, boxes: torch.Tensor, image_id: int) -> list[dict]:
    """Like D-FINE's own post-processing: the top scores over every (query, class) pair."""
    class_count = logits.shape[-1]
    scores, flat_indices = logits.sigmoid().flatten().topk(min(DETECTIONS_PER_IMAGE, logits.numel()))
    return [
        {
            "image_id": image_id,
            "category_id": int(index % class_count) + 1,
            "bbox": _xywh_pixels(boxes[index // class_count]),
            "score": float(score),
        }
        for score, index in zip(scores.cpu(), flat_indices.cpu(), strict=True)
    ]


@torch.no_grad()
def predictions(model, loader, device: torch.device) -> list[dict]:
    model.eval()
    results = []
    for pixels, targets in loader:
        outputs = model(pixel_values=pixels.to(device))
        for logits, boxes, target in zip(outputs.logits, outputs.pred_boxes, targets, strict=True):
            results.extend(_image_detections(logits.cpu(), boxes.cpu(), target["image_id"]))
    return results


def _class_scores(precision: np.ndarray, class_index: int) -> tuple[float | None, float | None]:
    """`precision` is COCOeval's [IoU threshold, recall, class, area range, max detections] table."""
    all_thresholds = precision[:, :, class_index, 0, -1]
    at_half = precision[0, :, class_index, 0, -1]
    if not (all_thresholds > -1).any():
        return None, None
    return float(all_thresholds[all_thresholds > -1].mean()), float(at_half[at_half > -1].mean())


def coco_metrics(val_file: Path, results: list[dict], labels: list[str]) -> dict:
    empty = {"map_50_95": 0.0, "map_50": 0.0, "per_class": {label: {"ap": None, "ap50": None} for label in labels}}
    with contextlib.redirect_stdout(io.StringIO()):
        truth = COCO(str(val_file))
        if not results or not truth.getAnnIds():
            return empty
        evaluation = COCOeval(truth, truth.loadRes(results), iouType="bbox")
        evaluation.evaluate()
        evaluation.accumulate()
        evaluation.summarize()
    precision = evaluation.eval["precision"]
    category_ids = evaluation.params.catIds
    per_class = {}
    for class_index, category_id in enumerate(category_ids):
        ap, ap50 = _class_scores(precision, class_index)
        per_class[labels[category_id - 1]] = {"ap": ap, "ap50": ap50}
    return {"map_50_95": float(evaluation.stats[0]), "map_50": float(evaluation.stats[1]), "per_class": per_class}


def evaluate(model, loader, val_file: Path, labels: list[str], device: torch.device) -> dict:
    return coco_metrics(val_file, predictions(model, loader, device), labels)
