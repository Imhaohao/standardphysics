"""The furniture that stayed put, and where a change sits relative to it.

Locations come from the geometry, not from a caption. A panoptic segmenter labels the
pixels of the before video, the labels are voted onto the 3D points that the pixels
see, and each category is split into connected pieces, so a sofa touching a table
stays two pieces. The words "on", "beside" and "between" are then decided by boxes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

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


# Words a vision model's name may use for a piece the segmenter put in each category.
NAME_FAMILIES = {
    "chair": {"chair", "armchair", "stool", "seat", "recliner"},
    "sofa": {"sofa", "couch", "settee", "loveseat"},
    "bed": {"bed"},
    "table": {"table", "desk"},
    "plant": {"plant", "pot", "succulent", "tree", "fern", "planter"},
    "television": {"television", "tv", "screen", "monitor"},
    "cabinet": {"cabinet", "table", "drawer", "drawers", "dresser", "sideboard", "nightstand", "chest", "console"},
    "shelf": {"shelf", "bookshelf", "bookcase", "shelving", "shelves"},
    "counter": {"counter", "bar", "worktop"},
    "bench": {"bench"},
    "oven": {"oven", "stove", "range", "cooker"},
    "fridge": {"fridge", "refrigerator"},
}


def fitting_name(category: str, proposed: str) -> str:
    """The model's more specific name when it agrees with the segmenter's category, else the category."""
    words = set(proposed.lower().replace("-", " ").split())
    return proposed if words & NAME_FAMILIES.get(category, {category}) else category


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
    detail: str = ""
    ambiguous: bool = False
    """Shares its name with something else in the room, so no sentence may point to it."""


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


# The longest footprint side each kind of furniture plausibly has. A "chair" 2.3 m long is
# a chair joined to its neighbours by the segmenter, and would mislead every sentence near it.
LONGEST_SIDE_M = {"chair": 1.3, "plant": 1.5, "television": 2.2, "bench": 2.5, "cabinet": 2.6, "shelf": 2.6,
                  "table": 2.8, "counter": 6.0, "sofa": 3.2, "bed": 2.6}


# The narrowest footprint side and the most elongated footprint each kind plausibly has. A
# "chair" 29 cm by 1.22 m is a sliver of something else, not a chair.
SHAPE = {"chair": (0.3, 1.9), "sofa": (0.45, 3.8), "table": (0.3, 4.5), "plant": (0.12, 2.5), "bed": (0.8, 2.5),
         "bench": (0.25, 6.0), "cabinet": (0.2, 6.0), "shelf": (0.15, 8.0)}


def kind_category(name: str) -> str | None:
    """The furniture kind a name's last word belongs to, if any: "wooden chair" is a chair."""
    words = name.lower().split()
    head = words[-1] if words else ""
    return next((category for category, family in NAME_FAMILIES.items() if head in family), None)


def fits_kind(box: Box, name: str) -> bool:
    """Whether a box could be the kind of thing its name says; names of no known kind always fit.

    A "chair" 1.3 m long has swallowed something beside it, and a "chair" 37 cm wide and
    1.2 m long is a strip of wall; neither is the chair it is called.
    """
    category = kind_category(name)
    if category is None:
        return True
    longest, shortest = float(box.size[:2].max()), float(box.size[:2].min())
    narrowest, most_elongated = SHAPE.get(category, (0.0, 10.0))
    return longest <= LONGEST_SIDE_M.get(category, 3.0) and shortest >= narrowest and longest <= most_elongated * shortest


def _is_furniture_sized(box: Box, count: int, category: str, rules: LandmarkRules) -> bool:
    longest, shortest = float(box.size[:2].max()), float(box.size[:2].min())
    narrowest, most_elongated = SHAPE.get(category, (rules.min_thickness_m, 10.0))
    return (count >= rules.min_points and longest >= rules.min_extent_m and shortest >= rules.min_thickness_m
            and longest <= LONGEST_SIDE_M.get(category, 3.0) and shortest >= narrowest
            and longest <= most_elongated * shortest)


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
        category = FURNITURE[class_name]
        for members in _pieces(points, ids, rules):
            found.extend(_sized_pieces(points, members, category, rules))
    return found


def _sized_pieces(points: np.ndarray, members: np.ndarray, category: str, rules: LandmarkRules,
                  split: bool = True) -> list[Landmark]:
    """A piece of furniture's size, or the pieces it falls into on a grid half as fine.

    Two pieces a few centimetres apart, such as a desk and the bench beside it, join on the
    coarse grid into one "table" too long to be a table; the finer grid separates them.
    """
    if len(members) < rules.min_points:
        return []
    box = fit_box(points[members])
    if _is_furniture_sized(box, len(members), category, rules):
        return [Landmark(members, box, category)]
    if not split or float(box.size[:2].max()) <= LONGEST_SIDE_M.get(category, 3.0):
        return []
    finer = replace(rules, voxel_m=rules.voxel_m / 2)
    return [piece for part in _pieces(points, members, finer)
            for piece in _sized_pieces(points, part, category, rules, split=False)]


def settle_kind(landmark: Landmark, model_name: str, rules: LandmarkRules = LandmarkRules()) -> bool:
    """Decide what kind of furniture a piece is when the segmenter and the vision model disagree.

    The segmenter often files a desk, a bench or a nightstand under a neighbouring class, while
    the vision model names it plainly. A name of another known kind wins when the piece has that
    kind's size and shape; a name of no known kind ("staircase") leaves the piece out.
    """
    if model_name == "object" or fitting_name(landmark.category, model_name) == model_name:
        return True
    for category in NAME_FAMILIES:
        if fitting_name(category, model_name) == model_name and _is_furniture_sized(
                landmark.box, len(landmark.point_ids), category, rules):
            landmark.category = category
            return True
    return False


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


def _same_kind_touching(landmark: Landmark, changes: list[tuple[Box, str]], reach_m: float = 0.1) -> bool:
    """A piece of the same kind as a change and touching it: most likely what that change left behind.

    An unmoved chair half a metre from a moved one is a real chair and stays.
    """
    family = NAME_FAMILIES.get(landmark.category, {landmark.category})
    return any(set(name.split()) & family and footprint_gap(landmark.box, box) <= reach_m for box, name in changes)


def apart_from(landmarks: list[Landmark], points: np.ndarray, changes: list[tuple[Box, str]]) -> list[Landmark]:
    """Drop pieces that are really part of a change, such as leaves left over from a plant that was taken away.

    A basket set on a table covers a corner of the table, so overlap alone is not enough;
    the piece has to sit inside the change, be mostly covered by it, or be the same kind of
    thing touching it, like a strip of a moved armchair that its old spot still shows.
    """
    return [lm for lm in landmarks if not any(_part_of_change(lm, points, box) for box, _ in changes)
            and not _same_kind_touching(lm, changes)]


def _belongs_to(piece: Landmark, host: Landmark, points: np.ndarray) -> bool:
    """Mostly inside the host's box, or touching a host of the same category."""
    if float(inside_box(points[piece.point_ids], host.box, margin_m=0.05).mean()) >= 0.5:
        return True
    return piece.category == host.category and footprint_gap(piece.box, host.box) <= 0.15


def _fits_together(piece: Landmark, host: Landmark, points: np.ndarray) -> bool:
    """Two dining chairs side by side would merge into one long "chair"; the size cap refuses that."""
    joined = fit_box(points[np.concatenate([host.point_ids, piece.point_ids])])
    return float(joined.size[:2].max()) <= LONGEST_SIDE_M.get(host.category, 3.0)


def merge_touching(landmarks: list[Landmark], points: np.ndarray) -> list[Landmark]:
    """One piece of furniture the segmenter split up, such as a side table seen as table and cabinet.

    A piece joins a larger one when most of it lies inside the larger one's box, or when the
    two touch and are the same kind of thing, so a coffee table pushed up against a sofa
    stays its own piece while two halves of one bookshelf become one.
    """
    pieces = sorted(landmarks, key=lambda landmark: -len(landmark.point_ids))
    merged: list[Landmark] = []
    for piece in pieces:
        host = next((m for m in merged if _belongs_to(piece, m, points) and _fits_together(piece, m, points)), None)
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


def touches_furniture(box: Box, landmarks: list[Landmark], reach_m: float = 0.1) -> bool:
    """Whether a box touches a piece of furniture both videos saw, so it is that piece's hidden side."""
    return any(footprint_gap(box, landmark.box) <= reach_m for landmark in landmarks)


def surface_top(heights: np.ndarray, bin_m: float = 0.02) -> float:
    """The height of a piece's top surface: its densest layer above its middle height.

    The highest points of a table are a stray handle or the base of whatever stands on it;
    a table top is a flat layer seen from above, so far more points share its height.
    """
    upper = heights[heights >= np.median(heights)]
    counts, edges = np.histogram(upper, bins=max(1, int(np.ceil((upper.max() - upper.min()) / bin_m))))
    densest = int(np.argmax(counts))
    return float(edges[densest + 1])


def supports_under(box: Box, landmarks: list[Landmark], points: np.ndarray) -> list[float]:
    """Top surfaces of the furniture whose footprint holds the centre of `box`."""
    return [surface_top(points[landmark.point_ids, 2]) for landmark in landmarks
            if _distance_to_footprint(box.center[:2], landmark.box) <= 0.02]


def _between(box: Box, near: list[tuple[float, Landmark]]) -> tuple[Landmark, Landmark] | None:
    for i, (_, first) in enumerate(near):
        for _, second in near[i + 1:]:
            a = first.box.center[:2] - box.center[:2]
            b = second.box.center[:2] - box.center[:2]
            cosine = a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)
            if cosine < -0.5 and first.name != second.name:
                return first, second
    return None


def place_phrase(box: Box, landmarks: list[Landmark], rules: LandmarkRules = LandmarkRules(), subject: str = "") -> str:
    """"on the coffee table", "between the sofa and the side table", "beside the bookshelf", or "".

    Furniture of the subject's own kind is never the reference: "the chair moved from beside
    the chair" tells the reader nothing, and such a piece is often what the change left behind.
    """
    kind = subject.split()[-1:]
    named = [lm for lm in landmarks if lm.name and lm.name != "object" and not lm.ambiguous
             and lm.name.split()[-1:] != kind]
    for landmark in named:
        if _rests_on(box, landmark.box, rules):
            return f"on the {landmark.name}"
    ranked = sorted(((footprint_gap(box, lm.box), lm) for lm in named if not _rests_on(lm.box, box, rules)),
                    key=lambda pair: pair[0])
    pair = _between(box, [(gap, lm) for gap, lm in ranked if gap <= rules.near_m])
    if pair:
        first, second = sorted(lm.name for lm in pair)
        return f"between the {first} and the {second}"
    if ranked and ranked[0][0] <= rules.beside_m:
        return f"beside the {ranked[0][1].name}"
    if ranked and ranked[0][0] <= rules.near_m:
        return f"near the {ranked[0][1].name}"
    return "on the open floor" if box.center[2] - box.size[2] / 2 < 0.15 else ""
