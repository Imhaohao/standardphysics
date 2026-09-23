"""The photo crop that best shows each kind of surface in a room.

A room's own materials are generated from what its photos show: the carpet as
it really is, not a generic floor. For every material key this finds the photo
that painted the most of that surface onto the scan, and crops the region those
points occupy in it, so the image model is shown the thing itself.
"""

from __future__ import annotations

import pathlib
from collections import Counter
from dataclasses import dataclass

import numpy as np
from PIL import Image

from .camera import PhotoCamera
from .scan_colour import ColouredScan

MIN_POINTS = 200
"""Photographed points a surface needs before a crop of it is worth sending."""
MIN_CROP_PIXELS = 96
CROP_PERCENTILES = (10.0, 90.0)
"""The central part of the surface's footprint, so stray points do not stretch the crop."""


@dataclass(frozen=True)
class ReferenceCrop:
    key: str
    frame_id: str
    image: Image.Image
    points: int
    box: tuple[int, int, int, int]


def _best_frame(sources: np.ndarray) -> tuple[str, int] | None:
    counts = Counter(frame for frame in sources if frame is not None)
    return counts.most_common(1)[0] if counts else None


def _crop_box(camera: PhotoCamera, points: np.ndarray) -> tuple[int, int, int, int] | None:
    columns, rows, depth = camera.project(points)
    visible = depth > 0
    if visible.sum() < MIN_POINTS:
        return None
    low, high = CROP_PERCENTILES
    left, right = np.percentile(columns[visible], [low, high])
    top, bottom = np.percentile(rows[visible], [low, high])
    box = (
        int(max(0, left)), int(max(0, top)),
        int(min(camera.width, right)), int(min(camera.height, bottom)),
    )
    if box[2] - box[0] < MIN_CROP_PIXELS or box[3] - box[1] < MIN_CROP_PIXELS:
        return None
    return box


def reference_crops(
    scan: ColouredScan,
    owners: np.ndarray,
    owner_keys: list[str],
    cameras: list[PhotoCamera],
    frame_paths: dict[str, pathlib.Path],
) -> list[ReferenceCrop]:
    """One crop per material key, from the photo that coloured most of that surface."""
    if scan.sources is None:
        raise ValueError("the scan must record which photo coloured each vertex")
    by_frame = {camera.frame_id: camera for camera in cameras}
    crops = []
    for key in sorted(set(owner_keys)):
        owned = np.isin(owners, [index for index, other in enumerate(owner_keys) if other == key]) & scan.seen
        best = _best_frame(scan.sources[owned])
        if best is None or best[1] < MIN_POINTS or best[0] not in by_frame:
            continue
        frame_id, count = best
        box = _crop_box(by_frame[frame_id], scan.vertices[owned & (scan.sources == frame_id)])
        if box is None:
            continue
        with Image.open(frame_paths[frame_id]) as photo:
            crops.append(ReferenceCrop(key, frame_id, photo.convert("RGB").crop(box), count, box))
    return crops
