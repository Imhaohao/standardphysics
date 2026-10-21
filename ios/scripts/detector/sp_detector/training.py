"""Fine-tunes D-FINE nano on the merged photos with a new class head.

The learning rate warms up, then follows a cosine curve over whichever runs out first: the step
budget (`SP_EPOCHS` or `SP_MAX_STEPS`) or the time budget (`SP_TRAIN_HOURS`). After every epoch
the model is scored on the validation split and the best one is kept.
"""

import json
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from transformers import DFineForObjectDetection

from sp_detector import base_model
from sp_detector.config import TrainingConfig
from sp_detector.evaluation import evaluate

BACKBONE_LEARNING_RATE_SCALE = 0.1
WEIGHT_DECAY = 1e-4
GRADIENT_CLIP = 0.1
MAXIMUM_WARMUP_STEPS = 500
LOG_EVERY_STEPS = 50


class CocoFileDataset(Dataset):
    """Photos from one of the files `splits.write_splits` made, already 640x640."""

    def __init__(self, annotation_file: Path, augment: bool):
        coco = json.loads(annotation_file.read_text())
        self.images = coco["images"]
        self.augment = augment
        self.boxes_by_image = {image["id"]: [] for image in self.images}
        for annotation in coco["annotations"]:
            self.boxes_by_image[annotation["image_id"]].append(annotation)

    def __len__(self) -> int:
        return len(self.images)

    def __getitem__(self, index: int):
        image = self.images[index]
        with Image.open(image["file_name"]) as photo:
            pixels = torch.frombuffer(bytearray(photo.convert("RGB").tobytes()), dtype=torch.uint8)
        pixels = pixels.reshape(base_model.INPUT_SIZE, base_model.INPUT_SIZE, 3).permute(2, 0, 1).float() / 255
        annotations = self.boxes_by_image[image["id"]]
        boxes = torch.tensor([_center_box(a["bbox"]) for a in annotations], dtype=torch.float32).reshape(-1, 4)
        classes = torch.tensor([a["category_id"] - 1 for a in annotations], dtype=torch.int64)
        if self.augment:
            pixels, boxes = _augmented(pixels, boxes)
        return pixels, {"class_labels": classes, "boxes": boxes, "image_id": image["id"]}


def _center_box(bbox: list[float]) -> list[float]:
    left, top, width, height = (value / base_model.INPUT_SIZE for value in bbox)
    return [left + width / 2, top + height / 2, width, height]


def _augmented(pixels: torch.Tensor, boxes: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    if random.random() < 0.5:
        pixels = pixels.flip(-1)
        boxes = boxes.clone()
        boxes[:, 0] = 1 - boxes[:, 0]
    brightness = random.uniform(0.75, 1.25)
    return (pixels * brightness).clamp(0, 1), boxes


def collate(batch):
    pixels, targets = zip(*batch, strict=True)
    return torch.stack(pixels), list(targets)


def training_device() -> torch.device:
    return torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def load_base_model(config: TrainingConfig, labels: list[str]) -> DFineForObjectDetection:
    source = config.base_model or base_model.REPO
    revision = None if config.base_model else base_model.REVISION
    return DFineForObjectDetection.from_pretrained(
        source,
        revision=revision,
        id2label=dict(enumerate(labels)),
        label2id={label: index for index, label in enumerate(labels)},
        ignore_mismatched_sizes=True,
    )


def make_optimizer(model: torch.nn.Module, learning_rate: float) -> torch.optim.Optimizer:
    backbone, rest = [], []
    for name, parameter in model.named_parameters():
        if parameter.requires_grad:
            (backbone if ".backbone." in name else rest).append(parameter)
    return torch.optim.AdamW(
        [
            {"params": backbone, "lr": learning_rate * BACKBONE_LEARNING_RATE_SCALE},
            {"params": rest, "lr": learning_rate},
        ],
        weight_decay=WEIGHT_DECAY,
    )


@dataclass
class Schedule:
    total_steps: int
    time_budget_seconds: float
    base_rates: list[float]
    started: float = field(default_factory=time.monotonic)
    step: int = 0

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started

    @property
    def progress(self) -> float:
        return max(self.step / self.total_steps, self.elapsed_seconds / self.time_budget_seconds)

    @property
    def is_finished(self) -> bool:
        return self.progress >= 1

    @property
    def learning_rate_factor(self) -> float:
        warmup_steps = max(1, min(MAXIMUM_WARMUP_STEPS, self.total_steps // 10))
        warmup = min(1.0, (self.step + 1) / warmup_steps)
        return warmup * 0.5 * (1 + math.cos(math.pi * min(1.0, self.progress)))


@dataclass
class TrainingResult:
    model_dir: Path
    metrics: dict
    epochs_completed: int
    steps: int
    elapsed_hours: float
    device: str


def _move_targets(targets: list[dict], device: torch.device) -> list[dict]:
    return [{"class_labels": t["class_labels"].to(device), "boxes": t["boxes"].to(device)} for t in targets]


def _train_step(model, optimizer, schedule: Schedule, batch, device) -> float:
    pixels, targets = batch
    for group, base_rate in zip(optimizer.param_groups, schedule.base_rates, strict=True):
        group["lr"] = base_rate * schedule.learning_rate_factor
    loss = model(pixel_values=pixels.to(device), labels=_move_targets(targets, device)).loss
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), GRADIENT_CLIP)
    optimizer.step()
    schedule.step += 1
    return loss.item()


def _log(schedule: Schedule, epoch: int, loss: float, images_per_step: int) -> None:
    if schedule.step % LOG_EVERY_STEPS and schedule.step != 1:
        return
    rate = schedule.step * images_per_step / max(schedule.elapsed_seconds, 1e-6)
    print(
        f"epoch {epoch} step {schedule.step}/{schedule.total_steps} loss {loss:.3f} "
        f"{rate:.1f} photos/s, {schedule.progress:.0%} of the budget used",
        flush=True,
    )


def _train_epoch(model, optimizer, schedule: Schedule, loader: DataLoader, device, epoch: int) -> None:
    model.train()
    for batch in loader:
        loss = _train_step(model, optimizer, schedule, batch, device)
        _log(schedule, epoch, loss, loader.batch_size)
        if schedule.is_finished:
            return


def train(config: TrainingConfig, train_file: Path, val_file: Path, labels: list[str]) -> TrainingResult:
    device = training_device()
    train_loader = DataLoader(
        CocoFileDataset(train_file, augment=True),
        batch_size=config.batch_size,
        shuffle=True,
        drop_last=True,
        num_workers=config.data_workers,
        collate_fn=collate,
        persistent_workers=config.data_workers > 0,
    )
    val_loader = DataLoader(
        CocoFileDataset(val_file, augment=False),
        batch_size=config.batch_size,
        num_workers=config.data_workers,
        collate_fn=collate,
    )
    if len(train_loader) == 0:
        raise ValueError(f"{train_file} has fewer photos than one batch of {config.batch_size}")
    model = load_base_model(config, labels).to(device)
    optimizer = make_optimizer(model, config.learning_rate)
    planned_steps = config.epochs * len(train_loader)
    total_steps = min(planned_steps, config.max_steps) if config.max_steps else planned_steps
    schedule = Schedule(
        total_steps=max(1, total_steps),
        time_budget_seconds=config.train_hours * 3600,
        base_rates=[group["lr"] for group in optimizer.param_groups],
    )
    print(f"Training on {device} with {len(train_loader.dataset)} photos, {schedule.total_steps} steps planned")

    model_dir = config.run_dir / "model"
    best_metrics, epoch = None, 0
    while not schedule.is_finished:
        epoch += 1
        _train_epoch(model, optimizer, schedule, train_loader, device, epoch)
        metrics = evaluate(model, val_loader, val_file, labels, device)
        print(f"epoch {epoch}: validation mAP@[.5:.95] {metrics['map_50_95']:.3f}, mAP@.5 {metrics['map_50']:.3f}")
        if best_metrics is None or metrics["map_50_95"] >= best_metrics["map_50_95"]:
            best_metrics = metrics | {"epoch": epoch}
            model.save_pretrained(model_dir)
    return TrainingResult(model_dir, best_metrics, epoch, schedule.step, schedule.elapsed_seconds / 3600, str(device))
