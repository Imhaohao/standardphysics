"""Regions cut out of the measured mesh, whether or not a scanner boxed them.

A scanner returns boxes for the categories it ships with, and everything else in
the room arrives as one continuous skin of triangles. This cuts the skin wherever
the surface turns or steps sharply, using the graph segmentation of Felzenszwalb
and Huttenlocher: neighbouring cells join unless the change between them is
larger than the variation already inside both groups.

The pieces are deliberately small. A chair comes back as its seat, back and
legs, because geometry alone cannot tell a chair pushed under a table from part
of the table, and joining the wrong pieces cannot be undone above this layer.
Gathering pieces into whole things is interpretation, which has the photos.

Each region is boxed along its own principal axes from the triangles it holds,
and its id comes from the cells it covers, so the same mesh gives the same ids
on every run.
"""

from __future__ import annotations

import pathlib
import uuid

import numpy as np
from standardphysics_contracts import Mat4

from ..lidar import room_faces
from .planes import CELL_METRES, face_measures, pool
from .regions import Region

GROUPING_SCALE = 0.6
"""How readily groups grow, in units of edge weight times cells (Felzenszwalb's k).
Larger joins more."""

SMALLEST_PIECE = 0.01
"""Square metres below which a piece is folded into a neighbour: a patch ten
centimetres on a side, about the face of a mug."""

STEP_WEIGHT = 1.0
"""How much a step along the surface's own facing counts, per cell of height,
against a turn of ninety degrees. Two parallel faces a cell apart, a book on a
desk, differ as much as a corner does."""

FORWARD = np.array(
    [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1) if (dx, dy, dz) > (0, 0, 0)]
)
"""Half of the 26 neighbouring offsets, so each pair of cells is visited once."""

REGION_NAMESPACE = uuid.UUID("5b3c1c4e-6f1d-4a43-9d55-2c7a8f0e9b21")


def segment(mesh: pathlib.Path, capture_to_room: Mat4) -> list[Region]:
    """The mesh cut into pieces at every sharp turn or step, as unnamed regions."""
    faces = room_faces(mesh, capture_to_room)
    if not len(faces):
        return []
    normals, centres, areas, keep = face_measures(faces)
    cells = pool(normals, centres, areas)
    first, second, weight = _edges(cells)
    label = _grouped(len(cells), first, second, weight, cells.area)
    return _fitted(faces[keep], label[cells.of_face])


def _edges(cells) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Every pair of touching cells, and how much the surface changes between them."""
    keys = _keys(cells.at)
    order = np.argsort(keys)
    ordered = keys[order]
    firsts, seconds = [], []
    for offset in FORWARD:
        wanted = _keys(cells.at + offset)
        slot = np.clip(np.searchsorted(ordered, wanted), 0, len(ordered) - 1)
        found = ordered[slot] == wanted
        firsts.append(np.flatnonzero(found))
        seconds.append(order[slot[found]])
    first, second = np.concatenate(firsts), np.concatenate(seconds)
    turn = 1.0 - np.abs(np.einsum("ij,ij->i", cells.facing[first], cells.facing[second]))
    rise = cells.middle[second] - cells.middle[first]
    step = np.abs(np.einsum("ij,ij->i", rise, cells.facing[first])) / CELL_METRES
    return first, second, turn + STEP_WEIGHT * step


def _keys(at: np.ndarray) -> np.ndarray:
    shifted = at.astype(np.int64) + (1 << 20)
    return (shifted[:, 0] << 42) | (shifted[:, 1] << 21) | shifted[:, 2]


def _grouped(count: int, first: np.ndarray, second: np.ndarray, weight: np.ndarray, area: np.ndarray) -> np.ndarray:
    """Felzenszwalb-Huttenlocher over the cells, then small pieces folded into a neighbour."""
    groups = _Groups(count, area)
    order = np.argsort(weight, kind="stable")
    pairs = list(zip(first[order].tolist(), second[order].tolist(), strict=True))
    for (a, b), w in zip(pairs, weight[order].tolist(), strict=True):
        groups.join_if_alike(a, b, w)
    for a, b in pairs:
        groups.fold_if_small(a, b)
    return groups.labels()


class _Groups:
    """Union-find carrying each group's size, area and largest internal change."""

    def __init__(self, count: int, area: np.ndarray):
        self.parent = list(range(count))
        self.cells = [1] * count
        self.area = area.tolist()
        self.inside = [0.0] * count

    def root(self, node: int) -> int:
        parent = self.parent
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def join_if_alike(self, a: int, b: int, weight: float) -> None:
        a, b = self.root(a), self.root(b)
        if a != b and weight <= min(self._tolerance(a), self._tolerance(b)):
            self._join(a, b, weight)

    def fold_if_small(self, a: int, b: int) -> None:
        a, b = self.root(a), self.root(b)
        if a != b and min(self.area[a], self.area[b]) < SMALLEST_PIECE:
            self._join(a, b, max(self.inside[a], self.inside[b]))

    def labels(self) -> np.ndarray:
        return np.array([self.root(node) for node in range(len(self.parent))], dtype=np.int64)

    def _tolerance(self, group: int) -> float:
        return self.inside[group] + GROUPING_SCALE / self.cells[group]

    def _join(self, a: int, b: int, weight: float) -> None:
        if self.cells[a] < self.cells[b]:
            a, b = b, a
        self.parent[b] = a
        self.cells[a] += self.cells[b]
        self.area[a] += self.area[b]
        self.inside[a] = max(self.inside[a], self.inside[b], weight)


def _fitted(faces: np.ndarray, labels: np.ndarray) -> list[Region]:
    order = np.argsort(labels, kind="stable")
    labels, faces = labels[order], faces[order]
    starts = np.flatnonzero(np.diff(labels, prepend=-1))
    ends = [*starts[1:], len(labels)]
    return [_boxed(faces[start:end].reshape(-1, 3)) for start, end in zip(starts, ends, strict=True)]


def _boxed(points: np.ndarray) -> Region:
    """The tightest box along the directions the points spread out in."""
    points = points.astype(np.float64)
    middle = points.mean(axis=0)
    _, _, directions = np.linalg.svd(points - middle, full_matrices=False)
    rotation = directions.T
    if np.linalg.det(rotation) < 0:
        rotation[:, 2] = -rotation[:, 2]
    local = (points - middle) @ rotation
    low, high = local.min(axis=0), local.max(axis=0)
    pose = np.eye(4)
    pose[:3, :3] = rotation
    pose[:3, 3] = middle + rotation @ ((low + high) / 2)
    return Region(id=_id_of(points), pose=pose, extents=high - low)


def _id_of(points: np.ndarray) -> uuid.UUID:
    places = np.unique(np.floor(points / CELL_METRES).astype(np.int64), axis=0)
    return uuid.uuid5(REGION_NAMESPACE, places.tobytes().hex())
