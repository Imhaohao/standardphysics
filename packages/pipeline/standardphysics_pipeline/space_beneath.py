"""What the LiDAR mesh saw under each raised piece, for knee and toe clearance.

ADA 2010 lets a turning space and a clear floor space reach under a table or a
counter as far as the knee and toe clearance under it goes (304.3.1, 305.4).
RoomPlan boxes a table as one block from the floor to its top, so the
occupancy grid never sees the open space under it. The mesh does, as far as
the phone looked: the floor under the table where the camera reached it, and
every leg, panel, apron, crossbar or pushed-in chair standing in the way.

This reads it once, at ingest, into a grid laid in each piece's own frame
(`SpaceBeneath`). It records what the mesh showed and decides nothing:
`knee_and_toe` decides what counts, with the numbers the rule pack holds.
"""

from __future__ import annotations

import base64
import functools
import math
import pathlib
import zlib
from dataclasses import dataclass

import numpy as np
from standardphysics_contracts import SceneGraph, SceneNode, SpaceBeneath, bounds_the_room

from .floor_coverage import (
    FLOOR_BAND,
    encode_cells,
    face_samples,
    faces_in_room,
    floor_coverage_from_faces,
    lying_on_the_floor,
)
from .footprints import rotation_about_z
from .lidar import load_mesh
from .occupancy import CELL_SIZE, blocks_floor, reads_as_wall

METHOD = 1
"""Bump when the rules below change, so a grid drawn by older rules is recognisable."""

SAMPLE_SPACING = CELL_SIZE / 2
"""How far apart points are spread over a face when finding the lowest surface over each cell.

It is half a cell, so a face that crosses a cell leaves a point in it."""

HIGHEST_RECORDED = 2.54
"""Metres: the most whole centimetres one byte holds. Nothing on a shop floor stands open higher."""

ON_THE_EDGE = 1e-3
"""How many cells past the grid's edge a point may fall and still land on it.

The mesh arrives in single precision, so a leg standing flush with the
footprint's edge reads a few millionths of a metre outside it, and the leg
still belongs to the piece."""

THINNEST_TOP = 0.025
"""Metres a piece's top is taken to be thick, for floor where the mesh shows nothing under it.

A phone held over a table sees its top and rarely its underside, so the space
under the top is only known to stop somewhere below it. The underside is put
an inch below the top there, rather than at the top itself. An apron, a panel
or a thicker top faces the camera from the side and shows as a surface, and
then that surface is what limits the space."""

TOUCHING = 0.001
"""Metres a floor face is drawn in toward its own middle before it marks cells.

A face whose edge only touches a cell has not seen that cell. Without this,
the floor just outside a table marks the first row under it as seen."""


def with_mesh_evidence(graph: SceneGraph, mesh_path: pathlib.Path, mesh_sha256: str) -> SceneGraph:
    """The graph carrying what its LiDAR mesh saw: the floor, and the space under each raised piece.

    Unchanged when the mesh cannot be read or the graph has no room frame to
    place it in. Both come from one read of the mesh, which for a walk through
    a library is most of a small server's memory.
    """
    mesh = load_mesh(mesh_path)
    if mesh is None or graph.capture_to_room is None:
        return graph
    faces = faces_in_room(mesh, graph.capture_to_room)
    graph = graph.model_copy(update={"floor_coverage": floor_coverage_from_faces(graph, faces, mesh_sha256)})
    return measure_space_beneath(graph, faces, mesh_sha256)


def raised_pieces(graph: SceneGraph) -> list[SceneNode]:
    """What the occupancy grid draws solid that is not the room itself, so any of it could stand over open floor."""
    return [
        node for node in graph.nodes
        if blocks_floor(node) and not bounds_the_room(node) and not reads_as_wall(node)
    ]


def measure_space_beneath(graph: SceneGraph, faces: np.ndarray, mesh_sha256: str) -> SceneGraph:
    """Every raised piece with what the mesh saw under it, from faces already in the room frame."""
    ground = graph.ground()
    pieces = raised_pieces(graph)
    if ground is None or not pieces or not len(faces):
        return graph
    floor_z = ground.transform.position.z
    pool = _FacePool.of(faces, floor_z, max(_top(node, floor_z) for node in pieces))
    measured = {node.id: _measure(node, pool, floor_z, mesh_sha256) for node in pieces}
    return graph.model_copy(update={"nodes": [
        node.model_copy(update={"space_beneath": measured[node.id]}) if node.id in measured else node
        for node in graph.nodes
    ]})


@dataclass(frozen=True)
class _FacePool:
    """The faces low enough to stand under some piece, each with the box around it so a piece finds its own fast."""

    faces: np.ndarray
    low: np.ndarray
    high: np.ndarray

    @classmethod
    def of(cls, faces: np.ndarray, floor_z: float, ceiling: float) -> _FacePool:
        heights = faces[:, :, 2]
        keep = (heights.max(axis=1) >= floor_z - FLOOR_BAND) & (heights.min(axis=1) <= floor_z + ceiling)
        kept = faces[keep]
        corners = (kept[:, 0], kept[:, 1], kept[:, 2])
        return cls(kept, np.minimum.reduce(corners), np.maximum.reduce(corners))

    def within(self, bounds: tuple[float, float, float, float], below: float) -> np.ndarray:
        """The faces whose boxes meet `bounds` in the plan and start lower than `below`."""
        x0, y0, x1, y1 = bounds
        hit = (
            (self.high[:, 0] >= x0) & (self.low[:, 0] <= x1)
            & (self.high[:, 1] >= y0) & (self.low[:, 1] <= y1)
            & (self.low[:, 2] <= below)
        )
        return self.faces[hit]


@dataclass(frozen=True)
class PieceFrame:
    """A piece's footprint in its own frame: its middle, which way it turns, and the cells across it."""

    x: float
    y: float
    cos: float
    sin: float
    half_x: float
    half_y: float

    @classmethod
    def of(cls, node: SceneNode) -> PieceFrame:
        cos_t, sin_t = rotation_about_z(node)
        p = node.transform.position
        return cls(p.x, p.y, cos_t, sin_t, node.dimensions.x / 2, node.dimensions.y / 2)

    @property
    def columns(self) -> int:
        return cells_across(2 * self.half_x)

    @property
    def rows(self) -> int:
        return cells_across(2 * self.half_y)

    def bounds(self, margin: float = 0.0) -> tuple[float, float, float, float]:
        """The room-frame box around the footprint, grown by `margin` on every side."""
        reach_x = abs(self.cos) * self.half_x + abs(self.sin) * self.half_y + margin
        reach_y = abs(self.sin) * self.half_x + abs(self.cos) * self.half_y + margin
        return self.x - reach_x, self.y - reach_y, self.x + reach_x, self.y + reach_y

    def to_local(self, faces: np.ndarray, floor_z: float) -> np.ndarray:
        """Faces moved into the piece's frame, heights measured from the floor."""
        dx, dy = faces[..., 0] - self.x, faces[..., 1] - self.y
        local = np.empty_like(faces)
        local[..., 0] = dx * self.cos + dy * self.sin
        local[..., 1] = -dx * self.sin + dy * self.cos
        local[..., 2] = faces[..., 2] - floor_z
        return local

    def cells(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The row and column of every local point, and which points land on the grid at all."""
        across = (points[:, 0] + self.half_x) / CELL_SIZE
        along = (points[:, 1] + self.half_y) / CELL_SIZE
        inside = (
            (across > -ON_THE_EDGE) & (across < self.columns + ON_THE_EDGE)
            & (along > -ON_THE_EDGE) & (along < self.rows + ON_THE_EDGE)
        )
        columns = np.clip(np.floor(across[inside]).astype(int), 0, self.columns - 1)
        rows = np.clip(np.floor(along[inside]).astype(int), 0, self.rows - 1)
        return rows, columns, inside


def cells_across(extent: float, cell: float = CELL_SIZE) -> int:
    """How many cells it takes to cover `extent` metres, at least one."""
    return max(1, math.ceil(round(extent / cell, 6)))


def _top(node: SceneNode, floor_z: float) -> float:
    """Metres from the floor to the piece's top, as low as either the box or the mesh puts it.

    The mesh's own scatter is allowed for once, when a height is compared with
    a limit (`knee_and_toe.HEIGHT_NOISE`), not again here.
    """
    box = node.transform.position.z + node.dimensions.z / 2 - floor_z
    measured = node.top_surface.height_m if node.top_surface is not None else None
    top = box if measured is None else min(box, measured)
    return float(np.clip(top, 0.0, HIGHEST_RECORDED))


def _measure(node: SceneNode, pool: _FacePool, floor_z: float, mesh_sha256: str) -> SpaceBeneath:
    frame = PieceFrame.of(node)
    top = _top(node, floor_z)
    faces = frame.to_local(pool.within(frame.bounds(margin=CELL_SIZE), floor_z + top), floor_z)
    floor = lying_on_the_floor(faces, 0.0)
    return SpaceBeneath(
        cell_size=CELL_SIZE,
        columns=frame.columns,
        rows=frame.rows,
        floor_seen=encode_cells(_floor_seen(faces[floor], frame)),
        open_cm=encode_centimetres(_open_heights(faces[~floor], frame, top)),
        mesh_sha256=mesh_sha256,
        method=METHOD,
    )


def _floor_seen(floor_faces: np.ndarray, frame: PieceFrame) -> np.ndarray:
    """The cells a floor face covers, not the ones it only touches."""
    seen = np.zeros((frame.rows, frame.columns), dtype=bool)
    rows, columns, _ = frame.cells(face_samples(_drawn_in(floor_faces[:, :, :2], TOUCHING)))
    seen[rows, columns] = True
    return seen


def _drawn_in(faces: np.ndarray, by: float) -> np.ndarray:
    """Every corner moved `by` metres toward its face's middle, or onto it when it is closer than that."""
    toward = faces.mean(axis=1, keepdims=True) - faces
    distance = np.linalg.norm(toward, axis=2, keepdims=True)
    return faces + toward * np.minimum(1.0, by / np.maximum(distance, 1e-12))


def _open_heights(faces: np.ndarray, frame: PieceFrame, top: float) -> np.ndarray:
    """Metres from the floor up to the lowest surface over each cell, never above the underside of the top.

    Only what stands clear of the floor band counts, because the floor itself
    is noisy by that much (see `FLOOR_BAND`).
    """
    open_to = np.full((frame.rows, frame.columns), max(top - THINNEST_TOP, 0.0))
    points = face_samples(faces, SAMPLE_SPACING)
    points = points[(points[:, 2] > FLOOR_BAND) & (points[:, 2] < top)]
    rows, columns, inside = frame.cells(points)
    np.minimum.at(open_to, (rows, columns), points[inside, 2])
    return open_to


def encode_centimetres(metres: np.ndarray) -> str:
    """Heights as whole centimetres, rounded down, one byte a cell: zlib, then base64."""
    centimetres = np.floor(np.clip(metres, 0.0, HIGHEST_RECORDED) * 100 + 1e-6).astype(np.uint8)
    return base64.b64encode(zlib.compress(centimetres.tobytes(), 9)).decode("ascii")


@functools.lru_cache(maxsize=256)
def decode_centimetres(encoded: str, rows: int, columns: int) -> np.ndarray:
    """The heights in metres, decoded once however many layouts ask about the same piece."""
    raw = np.frombuffer(zlib.decompress(base64.b64decode(encoded)), dtype=np.uint8)
    heights = raw.reshape(rows, columns) / 100.0
    heights.setflags(write=False)
    return heights
