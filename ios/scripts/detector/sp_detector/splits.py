"""Writes the merged photos as two COCO-format files, `train.json` and `val.json`.

Each photo is stretched once to the model's 640x640 input, as Vision does on the phone, and cached.
A photo lands in the validation split by a hash of its key, so reruns keep the same split.
"""

import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from sp_detector import base_model
from sp_detector.records import ImageRecord

SIZE = base_model.INPUT_SIZE
HASH_BUCKETS = 10_000


@dataclass(frozen=True)
class Splits:
    train_file: Path
    val_file: Path
    labels: list[str]
    train_instances: Counter
    val_instances: Counter


def is_validation(key: str, validation_fraction: float) -> bool:
    bucket = int(hashlib.sha1(key.encode()).hexdigest(), 16) % HASH_BUCKETS
    return bucket < validation_fraction * HASH_BUCKETS


def write_splits(records: list[ImageRecord], dataset_dir: Path, validation_fraction: float) -> Splits:
    labels = sorted({box.label for record in records for box in record.boxes})
    cached = _cache_resized(records, dataset_dir / "images")
    validation = [record for record in cached if is_validation(record.key, validation_fraction)]
    training = [record for record in cached if not is_validation(record.key, validation_fraction)]
    train_file, val_file = dataset_dir / "train.json", dataset_dir / "val.json"
    _write_coco(training, labels, train_file)
    _write_coco(validation, labels, val_file)
    return Splits(train_file, val_file, labels, _instances(training), _instances(validation))


def _instances(records: list[ImageRecord]) -> Counter:
    return Counter(box.label for record in records for box in record.boxes)


def _cache_resized(records: list[ImageRecord], cache_dir: Path) -> list[ImageRecord]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        resized = list(pool.map(lambda record: _resized(record, cache_dir), records))
    return [record for record in resized if record is not None]


def _resized(record: ImageRecord, cache_dir: Path) -> ImageRecord | None:
    target = cache_dir / f"{hashlib.sha1(record.key.encode()).hexdigest()}.jpg"
    if not target.exists():
        try:
            with Image.open(record.path) as image:
                image.convert("RGB").resize((SIZE, SIZE), Image.Resampling.BILINEAR).save(target, quality=90)
        except OSError as error:
            print(f"Skipping unreadable photo {record.path}: {error}")
            return None
    return ImageRecord(record.key, record.source, target, record.boxes)


def _write_coco(records: list[ImageRecord], labels: list[str], path: Path) -> None:
    category_ids = {label: index + 1 for index, label in enumerate(labels)}
    images, annotations = [], []
    for image_id, record in enumerate(records, start=1):
        images.append({"id": image_id, "file_name": str(record.path), "width": SIZE, "height": SIZE})
        for box in record.boxes:
            pixels = [box.left * SIZE, box.top * SIZE, box.width * SIZE, box.height * SIZE]
            annotations.append({
                "id": len(annotations) + 1,
                "image_id": image_id,
                "category_id": category_ids[box.label],
                "bbox": pixels,
                "area": pixels[2] * pixels[3],
                "iscrowd": 0,
            })
    categories = [{"id": category_id, "name": label} for label, category_id in category_ids.items()]
    path.write_text(json.dumps({"images": images, "annotations": annotations, "categories": categories}))
