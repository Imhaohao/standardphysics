"""The floor, rasterized, so clearance becomes a distance problem.

Every obstacle is an oriented box. A cell is occupied when its centre falls
inside one, tested in that box's own frame so rotation is handled exactly
rather than by an axis-aligned bounding box that would eat the corners.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import numpy as np

from standardphysics_contracts import SceneGraph, SceneNode, Vec3

CELL_SIZE = 0.025
"""25 mm. Fine enough that quantisation stays near half an inch."""

BLOCKING_HEIGHT = 0.23
"""A node blocks the floor when it rises above this.

9 inches is the toe clearance the standard allows beneath an obstruction, so
anything lower is something a footrest passes over: a floor mat, a threshold,
a cable cover. Anything taller is in the way.
"""

PASSABLE_KINDS = {"floor", "window", "opening", "door"}
"""Doors and openings are how you get through a wall, not obstacles."""


@dataclass(frozen=True)
class Grid:
    origin_x: float
    origin_y: float
    cell_size: float
    occupied: np.ndarray
    owner: np.ndarray
    """Index into `node_ids` for each occupied cell, -1 where free.

    A finding has to name the two objects forming a pinch, so the grid keeps
    track of who put each cell there.
    """

    node_ids: list[UUID] = field(default_factory=list)

    def owner_at(self, row: int, col: int) -> UUID | None:
        index = int(self.owner[row, col])
        return self.node_ids[index] if index >= 0 else None

    @property
    def shape(self) -> tuple[int, int]:
        return self.occupied.shape

    def to_cell(self, x: float, y: float) -> tuple[int, int]:
        col = int((x - self.origin_x) / self.cell_size)
        row = int((y - self.origin_y) / self.cell_size)
        return row, col

    def to_world(self, row: int, col: int) -> Vec3:
        return Vec3(
            x=self.origin_x + (col + 0.5) * self.cell_size,
            y=self.origin_y + (row + 0.5) * self.cell_size,
            z=0.0,
        )

    def contains(self, row: int, col: int) -> bool:
        rows, cols = self.occupied.shape
        return 0 <= row < rows and 0 <= col < cols


def blocks_floor(node: SceneNode) -> bool:
    if node.kind in PASSABLE_KINDS:
        return False
    top = node.transform.position.z + node.dimensions.z / 2
    return top > BLOCKING_HEIGHT


def _rotation_2d(node: SceneNode) -> tuple[float, float]:
    """Cosine and sine of the node's rotation about Z, from its transform."""
    m = node.transform.m
    cos_t, sin_t = m[0], m[4]
    scale = (cos_t * cos_t + sin_t * sin_t) ** 0.5
    if scale == 0:
        return 1.0, 0.0
    return cos_t / scale, sin_t / scale


def _bounds(graph: SceneGraph) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for node in graph.nodes:
        p = node.transform.position
        reach = max(node.dimensions.x, node.dimensions.y)
        xs += [p.x - reach, p.x + reach]
        ys += [p.y - reach, p.y + reach]
    return min(xs), min(ys), max(xs), max(ys)


def build_grid(graph: SceneGraph, cell_size: float = CELL_SIZE) -> Grid:
    min_x, min_y, max_x, max_y = _bounds(graph)
    cols = max(int(np.ceil((max_x - min_x) / cell_size)), 1)
    rows = max(int(np.ceil((max_y - min_y) / cell_size)), 1)
    occupied = np.zeros((rows, cols), dtype=bool)
    owner = np.full((rows, cols), -1, dtype=np.int32)
    node_ids: list[UUID] = []

    centres_x = min_x + (np.arange(cols) + 0.5) * cell_size
    centres_y = min_y + (np.arange(rows) + 0.5) * cell_size
    world_x, world_y = np.meshgrid(centres_x, centres_y)

    for node in graph.nodes:
        if not blocks_floor(node):
            continue
        node_ids.append(node.id)
        _mark(occupied, owner, len(node_ids) - 1, node, world_x, world_y)

    return Grid(min_x, min_y, cell_size, occupied, owner, node_ids)


def _mark(
    occupied: np.ndarray,
    owner: np.ndarray,
    index: int,
    node: SceneNode,
    world_x: np.ndarray,
    world_y: np.ndarray,
) -> None:
    """Occupy every cell whose centre lies inside this node's oriented box."""
    p = node.transform.position
    cos_t, sin_t = _rotation_2d(node)
    dx, dy = world_x - p.x, world_y - p.y
    local_x = dx * cos_t + dy * sin_t
    local_y = -dx * sin_t + dy * cos_t
    inside = (np.abs(local_x) <= node.dimensions.x / 2) & (
        np.abs(local_y) <= node.dimensions.y / 2
    )
    owner[inside & ~occupied] = index
    occupied |= inside
