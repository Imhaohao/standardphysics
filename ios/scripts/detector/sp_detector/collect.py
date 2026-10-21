"""Gathers the training photos: Open Images and COCO through the FiftyOne dataset zoo, plus any
COCO-format folders listed in `SP_EXTRA_COCO_DIRS`.

Each class is downloaded on its own so `SP_*_PER_CLASS` caps every class rather than the total.
The downloads are then read straight from disk, without FiftyOne's database, and a photo keeps
every box whose label the vocabulary knows, so a sink in a photo fetched for its mirror is still
labelled. Photos already downloaded by an earlier run are reused and included.
"""

import json
from collections.abc import Callable
from pathlib import Path

import fiftyone.utils.openimages as fouo
import fiftyone.zoo as foz

from sp_detector import sources
from sp_detector.config import TrainingConfig
from sp_detector.labels import COCO_CLASSES, OPEN_IMAGES_CLASSES, LabelVocabulary
from sp_detector.records import Box, ImageRecord
from sp_detector.sources import COCO_COMMERCIAL_LICENSE_IDS, DatasetSource

SAMPLING_SEED = 51
# COCO is fetched with headroom because photos under non-commercial licences are dropped afterwards.
COCO_OVERFETCH = 3


def _download(zoo_name: str, split: str, class_name: str, limit: int) -> Path:
    _, dataset_dir = foz.download_zoo_dataset(
        zoo_name,
        split=split,
        label_types=["detections"],
        classes=[class_name],
        max_samples=limit,
        shuffle=True,
        seed=SAMPLING_SEED,
    )
    return Path(dataset_dir) / split


def _download_each_class(zoo_name: str, split: str, class_names: tuple[str, ...], limit: int) -> Path | None:
    split_dir = None
    for class_name in class_names:
        split_dir = _download(zoo_name, split, class_name, limit)
    return split_dir


def _open_images_box(detection, vocabulary: LabelVocabulary) -> Box | None:
    """Open Images marks a box drawn around several objects as a group; those are left out."""
    label = vocabulary.label_for(detection.label)
    if label is None or getattr(detection, "IsGroupOf", False):
        return None
    return Box(label, *detection.bounding_box)


def _open_images_record(image_path: str, detections, vocabulary: LabelVocabulary) -> ImageRecord | None:
    found = detections.detections if detections else []
    boxes = tuple(box for detection in found if (box := _open_images_box(detection, vocabulary)) and box.is_visible)
    if not boxes:
        return None
    path = Path(image_path)
    return ImageRecord(f"open-images/{path.name}", "Open Images V7", path, boxes)


def open_images(config: TrainingConfig, vocabulary: LabelVocabulary) -> tuple[list[ImageRecord], DatasetSource]:
    source = sources.open_images_source()
    if config.open_images_per_class <= 0:
        return [], source
    split_dir = _download_each_class(
        "open-images-v7", config.open_images_split, OPEN_IMAGES_CLASSES, config.open_images_per_class
    )
    importer = fouo.OpenImagesV7DatasetImporter(dataset_dir=str(split_dir), label_types=["detections"])
    records = []
    with importer:
        for image_path, _, detections in importer:
            if record := _open_images_record(image_path, detections, vocabulary):
                records.append(record)
    return records, source


def _relative_box(annotation: dict, image: dict, label: str) -> Box:
    left, top, width, height = annotation["bbox"]
    return Box(label, left / image["width"], top / image["height"], width / image["width"], height / image["height"])


def coco_file_records(
    annotation_file: Path,
    images_dir: Path,
    source_name: str,
    vocabulary: LabelVocabulary,
    keep_image: Callable[[dict], bool] = lambda image: True,
) -> list[ImageRecord]:
    """Reads one COCO-format annotation file. Crowd boxes, like Open Images groups, are left out."""
    coco_file = json.loads(annotation_file.read_text())
    names = {category["id"]: category["name"] for category in coco_file["categories"]}
    images = {image["id"]: image for image in coco_file["images"] if keep_image(image)}
    boxes_by_image: dict[int, list[Box]] = {image_id: [] for image_id in images}
    for annotation in coco_file["annotations"]:
        label = vocabulary.label_for(names[annotation["category_id"]])
        image = images.get(annotation["image_id"])
        if label is None or image is None or annotation.get("iscrowd"):
            continue
        box = _relative_box(annotation, image, label)
        if box.is_visible:
            boxes_by_image[image["id"]].append(box)
    return [
        ImageRecord(f"{source_name}/{images[image_id]['file_name']}", source_name,
                    images_dir / images[image_id]["file_name"], tuple(boxes))
        for image_id, boxes in boxes_by_image.items()
        if boxes
    ]


def _allows_commercial_use(image: dict) -> bool:
    return image.get("license") in COCO_COMMERCIAL_LICENSE_IDS


def coco(config: TrainingConfig, vocabulary: LabelVocabulary) -> tuple[list[ImageRecord], DatasetSource]:
    """The zoo's `labels.json` is the COCO annotation file cut down to the downloaded photos."""
    source = sources.coco_source()
    if config.coco_per_class <= 0:
        return [], source
    split_dir = _download_each_class(
        "coco-2017", config.coco_split, COCO_CLASSES, config.coco_per_class * COCO_OVERFETCH
    )
    records = coco_file_records(
        split_dir / "labels.json", split_dir / "data", "coco", vocabulary, keep_image=_allows_commercial_use
    )
    return _capped_per_class(records, COCO_CLASSES, config.coco_per_class, vocabulary), source


def _capped_per_class(
    records: list[ImageRecord], class_names: tuple[str, ...], cap: int, vocabulary: LabelVocabulary
) -> list[ImageRecord]:
    """Up to `cap` photos showing each class, counting a photo only for the first class that takes it."""
    chosen: dict[str, ImageRecord] = {}
    for class_name in class_names:
        label = vocabulary.label_for(class_name)
        showing = [r for r in records if r.key not in chosen and any(box.label == label for box in r.boxes)]
        chosen.update((record.key, record) for record in showing[:cap])
    return list(chosen.values())


def _coco_files(folder: Path) -> list[Path]:
    return sorted(
        path for path in folder.rglob("*.json")
        if {"images", "annotations", "categories"} <= set(json.loads(path.read_text()))
    )


def extra_folders(config: TrainingConfig, vocabulary: LabelVocabulary) -> list[tuple[list[ImageRecord], DatasetSource]]:
    collected = []
    for folder in config.extra_coco_dirs:
        source = sources.extra_folder_source(folder)
        records = []
        for annotation_file in _coco_files(folder):
            source_name = f"{folder.name}/{annotation_file.parent.relative_to(folder)}"
            records += coco_file_records(annotation_file, annotation_file.parent, source_name, vocabulary)
        collected.append((records, source))
    return collected


def _note_usage(records: list[ImageRecord], source: DatasetSource) -> DatasetSource:
    source.image_count = len(records)
    source.labels = {box.label for record in records for box in record.boxes}
    return source


def all_records(config: TrainingConfig, vocabulary: LabelVocabulary) -> tuple[list[ImageRecord], list[DatasetSource]]:
    """Every photo once, with the sources that contributed photos."""
    gathered = [open_images(config, vocabulary), coco(config, vocabulary), *extra_folders(config, vocabulary)]
    unique: dict[str, ImageRecord] = {}
    used_sources = []
    for records, source in gathered:
        distinct = {record.key: record for record in records if record.key not in unique}
        unique.update(distinct)
        print(f"{source.name}: {len(distinct)} photos")
        if distinct:
            used_sources.append(_note_usage(list(distinct.values()), source))
    return list(unique.values()), used_sources
