"""Every setting of a training run, read from `SP_*` environment variables.

The defaults aim at one night (about 8 hours) on an Apple-silicon Mac: up to 1,000 Open Images
photos for each of the 11 Open Images classes and 300 COCO photos for each of the 19 COCO classes,
at most about 16,700 photos in all, trained until `SP_TRAIN_HOURS` runs out.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from sp_detector.labels import parse_renames


def _text(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _integer(name: str, default: int) -> int:
    return int(_text(name, str(default)))


def _number(name: str, default: float) -> float:
    return float(_text(name, str(default)))


def _paths(name: str) -> tuple[Path, ...]:
    return tuple(Path(part).expanduser().resolve() for part in _text(name, "").split(os.pathsep) if part)


@dataclass(frozen=True)
class TrainingConfig:
    work_dir: Path
    base_model: str | None
    open_images_split: str
    open_images_per_class: int
    coco_split: str
    coco_per_class: int
    extra_coco_dirs: tuple[Path, ...]
    label_renames: dict[str, str]
    validation_fraction: float
    batch_size: int
    epochs: int
    max_steps: int
    train_hours: float
    learning_rate: float
    data_workers: int
    skip_export: bool

    @classmethod
    def from_environment(cls, work_dir: Path) -> "TrainingConfig":
        return cls(
            work_dir=work_dir,
            base_model=os.environ.get("SP_BASE_MODEL"),
            open_images_split=_text("SP_OPEN_IMAGES_SPLIT", "train"),
            open_images_per_class=_integer("SP_OPEN_IMAGES_PER_CLASS", 1000),
            coco_split=_text("SP_COCO_SPLIT", "train"),
            coco_per_class=_integer("SP_COCO_PER_CLASS", 300),
            extra_coco_dirs=_paths("SP_EXTRA_COCO_DIRS"),
            label_renames=parse_renames(_text("SP_LABEL_RENAMES", "")),
            validation_fraction=_number("SP_VALIDATION_FRACTION", 0.1),
            batch_size=_integer("SP_BATCH_SIZE", 8),
            epochs=_integer("SP_EPOCHS", 30),
            max_steps=_integer("SP_MAX_STEPS", 0),
            train_hours=_number("SP_TRAIN_HOURS", 7.5),
            learning_rate=_number("SP_LEARNING_RATE", 2e-4),
            data_workers=_integer("SP_DATA_WORKERS", 4),
            skip_export=_text("SP_SKIP_EXPORT", "0") == "1",
        )

    @property
    def dataset_dir(self) -> Path:
        return self.work_dir / "dataset"

    @property
    def run_dir(self) -> Path:
        return self.work_dir / "run"
