"""One object, seen from several places, becoming one object.

The owner walks past a counter and the terminal on it is detected in a dozen
frames. Each of those is a separate rectangle carved into a separate box, and
the boxes overlap because they are the same terminal.

Two candidates join when their boxes overlap and their names agree. Agreement
is loose on purpose: "card reader" and "payment terminal" are the same object,
and a detector that alternates between them should not produce two. So a name
matches when either one contains the other's words.

The merged object is refitted from every point that fed it, which is what
makes a box built from several viewpoints tighter than any single view.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from .carve import CarvedBox, fit_box
from .detect import Detection

MIN_OVERLAP = 0.25
"""Share of the smaller box's volume that must lie inside the larger for two views to join."""
STOPWORDS = frozenset({"a", "an", "the", "of", "on", "small", "large", "black", "white"})


@dataclass(frozen=True)
class Candidate:
    detection: Detection
    box: CarvedBox


@dataclass(frozen=True)
class DiscoveredObject:
    name: str
    box: CarvedBox
    movable: bool
    confidence: float
    frame_ids: tuple[str, ...]

    @property
    def views(self) -> int:
        return len(self.frame_ids)


def merge_candidates(candidates: list[Candidate]) -> list[DiscoveredObject]:
    """Every candidate grouped into the objects they are views of, refitted from all their points."""
    groups = _group(candidates)
    merged = [_merged(group) for group in groups]
    return [object_ for object_ in merged if object_ is not None]


def _group(candidates: list[Candidate]) -> list[list[Candidate]]:
    parent = list(range(len(candidates)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for first in range(len(candidates)):
        for second in range(first + 1, len(candidates)):
            if _same_object(candidates[first], candidates[second]):
                parent[root(first)] = root(second)

    grouped: dict[int, list[Candidate]] = {}
    for index, candidate in enumerate(candidates):
        grouped.setdefault(root(index), []).append(candidate)
    return list(grouped.values())


def _same_object(first: Candidate, second: Candidate) -> bool:
    return _names_agree(first.detection.name, second.detection.name) and _overlaps(first.box, second.box)


def _names_agree(first: str, second: str) -> bool:
    left, right = _words(first), _words(second)
    return bool(left and right and (left <= right or right <= left))


def _words(name: str) -> frozenset[str]:
    return frozenset(word for word in name.lower().split() if word not in STOPWORDS)


def _overlaps(first: CarvedBox, second: CarvedBox) -> bool:
    """Axis-aligned intersection against the smaller box, which is orientation-free and cheap."""
    smaller = min(first.volume, second.volume)
    if smaller <= 0:
        return False
    lows = [_bounds(box)[0] for box in (first, second)]
    highs = [_bounds(box)[1] for box in (first, second)]
    overlap = np.maximum(0.0, np.minimum(highs[0], highs[1]) - np.maximum(lows[0], lows[1]))
    return float(np.prod(overlap)) / smaller >= MIN_OVERLAP


def _bounds(box: CarvedBox) -> tuple[np.ndarray, np.ndarray]:
    """The axis-aligned range the turned box occupies."""
    half = np.asarray(box.dimensions, dtype=np.float64) / 2
    cos_t, sin_t = abs(np.cos(box.yaw)), abs(np.sin(box.yaw))
    reach = np.asarray([
        half[0] * cos_t + half[1] * sin_t,
        half[0] * sin_t + half[1] * cos_t,
        half[2],
    ])
    centre = np.asarray(box.centre, dtype=np.float64)
    return centre - reach, centre + reach


def _merged(group: list[Candidate]) -> DiscoveredObject | None:
    box = fit_box(np.concatenate([candidate.box.points for candidate in group], axis=0))
    if box is None:
        return None
    weight: Counter[str] = Counter()
    for candidate in group:
        weight[candidate.detection.name] += candidate.detection.confidence
    name = weight.most_common(1)[0][0]
    movable = sum(candidate.detection.movable for candidate in group) * 2 >= len(group)
    return DiscoveredObject(
        name=name,
        box=box,
        movable=movable,
        confidence=max(candidate.detection.confidence for candidate in group),
        frame_ids=tuple(sorted({candidate.detection.frame_id for candidate in group})),
    )
