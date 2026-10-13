"""The furniture that stayed put, and where a change sits relative to it.

Locations come from the geometry, not from a caption. A panoptic segmenter labels the
pixels of the before video, the labels are voted onto the 3D points that the pixels
see, and each category is split into connected pieces, so a sofa touching a table
stays two pieces. The words "on", "beside" and "between" are then decided by boxes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import label

from .evidence import KEPT, DepthLookup, Tolerance, compare
from .geometry import project
from .regions import Box, fit_box
from .views import View

FURNITURE = {
    "chair": "chair", "couch": "sofa", "bed": "bed", "dining table": "table", "table-merged": "table",
    "potted plant": "plant", "tv": "television", "refrigerator": "fridge", "oven": "oven", "sink": "sink",
    "toilet": "toilet", "bench": "bench", "cabinet-merged": "cabinet", "shelf": "shelf", "counter": "counter",
    "suitcase": "suitcase",
}


@dataclass(frozen=True)
class LandmarkRules:
    voxel_m: float = 0.05
    floor_m: float = 0.05
    min_points: int = 250
    min_extent_m: float = 0.25
    min_thickness_m: float = 0.12
    beside_m: float = 0.5
    near_m: float = 1.5
    on_top_m: float = 0.1


@dataclass
class Landmark:
    point_ids: np.ndarray
    box: Box
    category: str
    name: str = ""


def vote_classes(points: np.ndarray, views: list[View], class_maps: list[np.ndarray],
                 tolerance: Tolerance = Tolerance()) -> np.ndarray:
    """Each point's most common pixel label across the views that see its surface, or -1."""
    keys = []
    for view, classes in zip(views, class_maps):
        agree, _, _ = compare(points, DepthLookup.of(view, tolerance), tolerance)
        u, v, _ = project(points[agree], view)
        labels = classes[v.astype(int), u.astype(int)]
        seen = np.flatnonzero(agree)[labels >= 0]
        keys.append(seen.astype(np.int64) * 1000 + labels[labels >= 0])
    winner = np.full(len(points), -1, dtype=np.int32)
    if not keys:
        return winner
    pairs, counts = np.unique(np.concatenate(keys), return_counts=True)
    order = np.lexsort((-counts, pairs // 1000))
    point_ids, firsts = np.unique(pairs[order] // 1000, return_index=True)
    winner[point_ids] = (pairs[order][firsts] % 1000).astype(np.int32)
    return winner


def _pieces(points: np.ndarray, ids: np.ndarray, rules: LandmarkRules) -> list[np.ndarray]:
    cells = np.floor((points[ids] - points[ids].min(axis=0)) / rules.voxel_m).astype(np.int64)
    grid = np.zeros(tuple(cells.max(axis=0) + 1), dtype=bool)
    grid[tuple(cells.T)] = True
    labels, count = label(grid, np.ones((3, 3, 3), dtype=bool))
    point_labels = labels[tuple(cells.T)]
    return [ids[point_labels == index] for index in range(1, count + 1)]


def _is_furniture_sized(box: Box, count: int, rules: LandmarkRules) -> bool:
    return (count >= rules.min_points and float(box.size[:2].max()) >= rules.min_extent_m
            and float(box.size[:2].min()) >= rules.min_thickness_m)


def find_landmarks(points: np.ndarray, status: np.ndarray, classes: np.ndarray, names: dict[int, str],
                   ceiling_m: float, rules: LandmarkRules = LandmarkRules()) -> list[Landmark]:
    """Connected pieces of unchanged furniture, one category at a time."""
    standing = (status == KEPT) & (points[:, 2] > rules.floor_m) & (points[:, 2] < ceiling_m)
    found = []
    for class_id, class_name in names.items():
        if class_name not in FURNITURE:
            continue
        ids = np.flatnonzero(standing & (classes == class_id))
        if len(ids) < rules.min_points:
            continue
        for members in _pieces(points, ids, rules):
            box = fit_box(points[members]) if len(members) >= rules.min_points else None
            if box is not None and _is_furniture_sized(box, len(members), rules):
                found.append(Landmark(members, box, FURNITURE[class_name]))
    return found


def inside_box(points: np.ndarray, box: Box, margin_m: float = 0.05) -> np.ndarray:
    c, s = np.cos(-box.yaw), np.sin(-box.yaw)
    offset = points - box.center
    local_xy = offset[:, :2] @ np.array([[c, s], [-s, c]])
    half = box.size / 2 + margin_m
    return np.all(np.abs(local_xy) <= half[:2], axis=1) & (np.abs(offset[:, 2]) <= half[2])


def _part_of_change(landmark: Landmark, points: np.ndarray, box: Box) -> bool:
    reach = float(box.size[:2].max()) / 2 + 0.25
    close = float(np.linalg.norm(landmark.box.center[:2] - box.center[:2])) <= reach
    similar_size = float(landmark.box.size[:2].max()) <= 2 * float(box.size[:2].max())
    return (close and similar_size) or float(inside_box(points[landmark.point_ids], box).mean()) > 0.5


def apart_from(landmarks: list[Landmark], points: np.ndarray, boxes: list[Box]) -> list[Landmark]:
    """Drop pieces that are really part of a change, such as leaves left over from a plant that was taken away.

    A basket set on a table covers a corner of the table, so overlap alone is not enough;
    the piece has to sit inside the change or be mostly covered by it.
    """
    return [lm for lm in landmarks if not any(_part_of_change(lm, points, box) for box in boxes)]


def _mostly_inside(piece: Landmark, host: Landmark, points: np.ndarray, share: float = 0.5) -> bool:
    return float(inside_box(points[piece.point_ids], host.box, margin_m=0.05).mean()) >= share


def merge_touching(landmarks: list[Landmark], points: np.ndarray) -> list[Landmark]:
    """One piece of furniture the segmenter split in two, such as a side table seen as table and cabinet.

    A piece joins a larger one only when most of it lies inside the larger one's box, so a
    coffee table pushed up against a sofa stays its own piece.
    """
    pieces = sorted(landmarks, key=lambda landmark: -len(landmark.point_ids))
    merged: list[Landmark] = []
    for piece in pieces:
        host = next((m for m in merged if _mostly_inside(piece, m, points)), None)
        if host is None:
            merged.append(piece)
            continue
        host.point_ids = np.concatenate([host.point_ids, piece.point_ids])
        host.box = fit_box(points[host.point_ids])
    return merged


def _footprint_corners(box: Box) -> np.ndarray:
    return box.corners()[:4, :2]


def _distance_to_footprint(xy: np.ndarray, box: Box) -> np.ndarray:
    c, s = np.cos(-box.yaw), np.sin(-box.yaw)
    local = (xy - box.center[:2]) @ np.array([[c, s], [-s, c]])
    return np.linalg.norm(np.maximum(np.abs(local) - box.size[:2] / 2, 0), axis=-1)


def footprint_gap(a: Box, b: Box) -> float:
    """Floor distance between two upright boxes' footprints, zero where they overlap."""
    return float(min(_distance_to_footprint(_footprint_corners(a), b).min(),
                     _distance_to_footprint(_footprint_corners(b), a).min(),
                     _distance_to_footprint(a.center[:2], b), _distance_to_footprint(b.center[:2], a)))


def crossed(landmarks: list[Landmark], start: np.ndarray, end: np.ndarray, reach_m: float = 0.35) -> str:
    """A piece the move went past, so the object ended up on its other side."""
    route = end[:2] - start[:2]
    length = float(np.linalg.norm(route))
    for landmark in landmarks:
        along = float((landmark.box.center[:2] - start[:2]) @ route / max(length ** 2, 1e-9))
        nearest = start[:2] + np.clip(along, 0, 1) * route
        if 0.2 < along < 0.8 and float(_distance_to_footprint(nearest, landmark.box)) <= reach_m:
            return landmark.name
    return ""


def heading(landmarks: list[Landmark], start: np.ndarray, end: np.ndarray, min_cosine: float = 0.9) -> str:
    """The piece the object moved straight toward, if one lies along its path."""
    route = end[:2] - start[:2]
    best, best_cosine = "", min_cosine
    for landmark in landmarks:
        toward = landmark.box.center[:2] - start[:2]
        cosine = float(route @ toward / (np.linalg.norm(route) * np.linalg.norm(toward) + 1e-9))
        if cosine > best_cosine:
            best, best_cosine = landmark.name, cosine
    return best


def _rests_on(box: Box, base: Box, rules: LandmarkRules) -> bool:
    bottom = box.center[2] - box.size[2] / 2
    top = base.center[2] + base.size[2] / 2
    c, s = np.cos(-base.yaw), np.sin(-base.yaw)
    local = np.array([[c, -s], [s, c]]) @ (box.center[:2] - base.center[:2])
    inside = np.all(np.abs(local) <= base.size[:2] / 2 + 0.05)
    return bool(inside and abs(bottom - top) < rules.on_top_m and bottom > 0.15)


def _between(box: Box, near: list[tuple[float, Landmark]]) -> tuple[Landmark, Landmark] | None:
    for i, (_, first) in enumerate(near):
        for _, second in near[i + 1:]:
            a = first.box.center[:2] - box.center[:2]
            b = second.box.center[:2] - box.center[:2]
            cosine = a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)
            if cosine < -0.5 and first.name != second.name:
                return first, second
    return None


def place_phrase(box: Box, landmarks: list[Landmark], rules: LandmarkRules = LandmarkRules()) -> str:
    """"on the coffee table", "between the sofa and the side table", "beside the bookshelf", or ""."""
    named = [landmark for landmark in landmarks if landmark.name and landmark.name != "object"]
    for landmark in named:
        if _rests_on(box, landmark.box, rules):
            return f"on the {landmark.name}"
    ranked = sorted(((footprint_gap(box, lm.box), lm) for lm in named if not _rests_on(lm.box, box, rules)),
                    key=lambda pair: pair[0])
    pair = _between(box, [(gap, lm) for gap, lm in ranked if gap <= rules.near_m])
    if pair:
        return f"between the {pair[0].name} and the {pair[1].name}"
    if ranked and ranked[0][0] <= rules.beside_m:
        return f"beside the {ranked[0][1].name}"
    if ranked and ranked[0][0] <= rules.near_m:
        return f"near the {ranked[0][1].name}"
    return "on the open floor" if box.center[2] - box.size[2] / 2 < 0.15 else ""
