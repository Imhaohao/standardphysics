"""Splitting a frustum of points into the separate things standing in it.

A rectangle drawn around a card reader also contains the counter below it, the
wall behind it and whatever is beside it. Depth alone does not separate those:
a floor running away from the camera fills every depth band continuously, so
growing a band from the nearest bin walks all the way to the far wall.

What does separate them is space. Once the walls, the floor and everything
RoomPlan already measured are taken out, the leftovers stand apart from each
other by real gaps, and points that touch through a six-centimetre grid belong
to the same thing.

Of those pieces, the one the detector meant is the one that fills its
rectangle. A piece covering a tenth of the rectangle is something glimpsed
past the edge of the object; the piece whose own outline matches the drawn
outline is the object.
"""

from __future__ import annotations

import numpy as np

from .detect import Detection

CLUSTER_VOXEL = 0.06
"""Points within one cell of each other are the same object. Wider than the mesh
is dense, narrower than the gap between a terminal and the screen beside it."""
MIN_CLUSTER_POINTS = 20
NEIGHBOURS = tuple(
    (dx, dy, dz)
    for dx in (0, 1)
    for dy in (-1, 0, 1)
    for dz in (-1, 0, 1)
    if (dx, dy, dz) > (0, 0, 0)
)
"""Half of the 26 directions; the other half comes free from symmetry."""


def voxel_components(points: np.ndarray, voxel: float = CLUSTER_VOXEL) -> np.ndarray:
    """A component label per point, joining points that share or touch a voxel."""
    if not len(points):
        return np.zeros(0, dtype=np.int64)
    cells = np.floor(points / voxel).astype(np.int64)
    unique, inverse = np.unique(cells, axis=0, return_inverse=True)
    parent = np.arange(len(unique))
    lookup = {tuple(cell): index for index, cell in enumerate(unique)}
    for offset in NEIGHBOURS:
        _join_along(parent, unique, lookup, offset)
    roots = np.asarray([_root(parent, index) for index in range(len(unique))])
    return roots[inverse]


def _join_along(parent: np.ndarray, unique: np.ndarray, lookup: dict, offset: tuple[int, int, int]) -> None:
    shifted = unique + np.asarray(offset, dtype=np.int64)
    for index, cell in enumerate(shifted):
        neighbour = lookup.get(tuple(cell))
        if neighbour is not None:
            _union(parent, index, neighbour)


def _root(parent: np.ndarray, index: int) -> int:
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return int(index)


def _union(parent: np.ndarray, first: int, second: int) -> None:
    first_root, second_root = _root(parent, first), _root(parent, second)
    if first_root != second_root:
        parent[first_root] = second_root


def dominant_cluster(
    points: np.ndarray,
    columns: np.ndarray,
    rows: np.ndarray,
    detection: Detection,
    voxel: float = CLUSTER_VOXEL,
) -> np.ndarray:
    """The piece whose outline best matches the rectangle the detector drew."""
    labels = voxel_components(points, voxel)
    best_score, best = 0.0, np.zeros(len(points), dtype=bool)
    for label in np.unique(labels):
        member = labels == label
        if member.sum() < MIN_CLUSTER_POINTS:
            continue
        score = _fills(columns[member], rows[member], detection)
        if score > best_score:
            best_score, best = score, member
    return best


def _fills(columns: np.ndarray, rows: np.ndarray, detection: Detection) -> float:
    """How much of the rectangle this piece explains, and how much of it stays inside.

    A cluster is rewarded for covering the rectangle and penalised for
    spilling past it, so neither a speck in the corner nor the whole room wins.
    """
    left, top, right, bottom = detection.box
    piece = (
        max(0.0, float(columns.max() - columns.min())),
        max(0.0, float(rows.max() - rows.min())),
    )
    overlap = (
        max(0.0, min(float(columns.max()), right) - max(float(columns.min()), left)),
        max(0.0, min(float(rows.max()), bottom) - max(float(rows.min()), top)),
    )
    shared = overlap[0] * overlap[1]
    union = detection.width * detection.height + piece[0] * piece[1] - shared
    return shared / union if union > 0 else 0.0
