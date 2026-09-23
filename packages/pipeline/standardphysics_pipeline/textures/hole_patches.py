"""Patching the holes the LiDAR left in walls and floors with the planes they lie on.

A phone's LiDAR misses dark, shiny and distant surfaces, so a scanned room is
full of holes: on one office the scan had no surface over a quarter of the
walls and most of the floor. The measured model knows where every wall and the
floor are, and a wall does not stop where the scanner stopped seeing it, so
each hole in a sheet is patched with small squares lying on that sheet's plane.
The patches are coloured in the same pass as the scan, which is what lets a
photo that saw the floor the LiDAR missed paint it.

Display only. Patches go into the picture of the room and nowhere else: every
check still measures the LiDAR mesh as captured.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import Delaunay, QhullError, cKDTree
from standardphysics_contracts import SceneGraph, SceneNode, bounds_the_room, stands_upright

CELL = 0.05
"""Patch size in metres: finer than a photo resolves from across a room."""
HOLE_DISTANCE = 0.06
"""A cell is a hole when no scanned vertex lies within this distance of its centre."""
OPENING_MARGIN = 0.02
WALL_TOLERANCE = 0.05
"""How far past the wall line, in metres, a floor patch may still sit."""
SEGMENT_EPSILON = 1e-9


@dataclass(frozen=True)
class PatchedGeometry:
    vertices: np.ndarray
    triangles: np.ndarray
    inferred: np.ndarray
    """Whether each vertex belongs to a patch rather than to the scan."""


@dataclass(frozen=True)
class _Sheet:
    rotation: np.ndarray
    centre: np.ndarray
    half: np.ndarray
    across: int
    up: int
    """The two in-plane axes of the sheet's own frame."""
    normal: np.ndarray
    """The sheet's normal, turned to face into the room."""


def _sheet(node: SceneNode, room_centre: np.ndarray) -> _Sheet:
    matrix = np.asarray(node.transform.m, dtype=np.float64).reshape(4, 4)
    rotation, centre = matrix[:3, :3], matrix[:3, 3]
    half = np.array([node.dimensions.x, node.dimensions.y, node.dimensions.z]) / 2
    thin = int(np.argmin(half))
    across, up = (axis for axis in range(3) if axis != thin)
    normal = rotation[:, thin]
    if not stands_upright(node):
        normal = normal if normal[2] >= 0 else -normal
    elif np.dot(room_centre - centre, normal) < 0:
        normal = -normal
    return _Sheet(rotation, centre, half, across, up, normal)


def _cell_centres(sheet: _Sheet) -> np.ndarray:
    """Cell centres covering the sheet, in its own frame."""
    along_across = np.arange(-sheet.half[sheet.across] + CELL / 2, sheet.half[sheet.across], CELL)
    along_up = np.arange(-sheet.half[sheet.up] + CELL / 2, sheet.half[sheet.up], CELL)
    grid_across, grid_up = np.meshgrid(along_across, along_up)
    local = np.zeros((grid_across.size, 3))
    local[:, sheet.across] = grid_across.ravel()
    local[:, sheet.up] = grid_up.ravel()
    return local


def _to_room(sheet: _Sheet, local: np.ndarray) -> np.ndarray:
    return local @ sheet.rotation.T + sheet.centre


def _inside_openings(points: np.ndarray, openings: list[SceneNode]) -> np.ndarray:
    """Points that fall in a door or window cut into the sheet, which must stay open."""
    blocked = np.zeros(len(points), dtype=bool)
    for opening in openings:
        matrix = np.asarray(opening.transform.m, dtype=np.float64).reshape(4, 4)
        half = np.array([opening.dimensions.x, opening.dimensions.y, opening.dimensions.z]) / 2
        local = (points - matrix[:3, 3]) @ matrix[:3, :3]
        blocked |= np.all(np.abs(local) <= half + OPENING_MARGIN, axis=1)
    return blocked


def _squares(sheet: _Sheet, centres_local: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two triangles per cell, wound so their normal faces into the room."""
    corners = []
    for step_across, step_up in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        offset = np.zeros(3)
        offset[sheet.across], offset[sheet.up] = step_across * CELL / 2, step_up * CELL / 2
        corners.append(_to_room(sheet, centres_local + offset))
    vertices = np.stack(corners, axis=1).reshape(-1, 3)
    first = np.arange(len(centres_local)) * 4
    triangles = np.concatenate([
        np.stack([first, first + 1, first + 2], axis=1),
        np.stack([first, first + 2, first + 3], axis=1),
    ])
    facing = np.cross(vertices[triangles[0, 1]] - vertices[triangles[0, 0]], vertices[triangles[0, 2]] - vertices[triangles[0, 0]])
    if len(triangles) and np.dot(facing, sheet.normal) < 0:
        triangles = triangles[:, ::-1]
    return vertices, triangles


def _openings_of(node: SceneNode, graph: SceneGraph) -> list[SceneNode]:
    """Doors and windows cut into the sheet. A whiteboard attached to it is not a hole."""
    return [other for other in graph.nodes if other.parent_id == node.id and other.relation == "cut_into"]


def _walled_area(sheets: list[SceneNode]) -> Delaunay | None:
    """The floor plan the walls enclose, as the hull of their ends, or None without walls.

    A measured floor can run past the walls into the space next door, and a patch
    out there would be painted with whatever a photo saw through the doorway.
    """
    ends = []
    for node in sheets:
        if not stands_upright(node):
            continue
        matrix = np.asarray(node.transform.m, dtype=np.float64).reshape(4, 4)
        half = np.array([node.dimensions.x, node.dimensions.y, node.dimensions.z]) / 2
        run = int(np.argmax(half * (np.abs(matrix[2, :3]) < 0.5)))
        for sign in (-1.0, 1.0):
            ends.append((matrix[:3, :3][:, run] * half[run] * sign + matrix[:3, 3])[:2])
    try:
        return Delaunay(np.asarray(ends)) if len(ends) >= 3 else None
    except QhullError:
        return None


def _outside_the_walls(centres: np.ndarray, node: SceneNode, walled: Delaunay | None) -> np.ndarray:
    if walled is None or stands_upright(node):
        return np.zeros(len(centres), dtype=bool)
    return walled.find_simplex(centres[:, :2], tol=WALL_TOLERANCE) < 0


def patches_for(vertices: np.ndarray, graph: SceneGraph) -> tuple[np.ndarray, np.ndarray]:
    """Squares covering every stretch of wall and floor the scan has no surface on."""
    sheets = [node for node in graph.nodes if bounds_the_room(node) and node.parent_id is None]
    if not sheets or not len(vertices):
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.int64)
    scanned = cKDTree(vertices)
    room_centre = vertices.mean(axis=0)
    walled = _walled_area(sheets)
    all_vertices, all_triangles, offset = [], [], 0
    for node in sheets:
        sheet = _sheet(node, room_centre)
        local = _cell_centres(sheet)
        centres = _to_room(sheet, local)
        hole = scanned.query(centres)[0] > HOLE_DISTANCE
        hole &= ~_inside_openings(centres, _openings_of(node, graph))
        hole &= ~_outside_the_walls(centres, node, walled)
        if not hole.any():
            continue
        square_vertices, square_triangles = _squares(sheet, local[hole])
        all_vertices.append(square_vertices)
        all_triangles.append(square_triangles + offset)
        offset += len(square_vertices)
    if not all_vertices:
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.int64)
    return np.concatenate(all_vertices), np.concatenate(all_triangles)


def with_holes_patched(vertices: np.ndarray, triangles: np.ndarray, graph: SceneGraph) -> PatchedGeometry:
    """The scan with its wall and floor holes patched, and which vertices are patches."""
    patch_vertices, patch_triangles = patches_for(vertices, graph)
    return PatchedGeometry(
        vertices=np.concatenate([vertices, patch_vertices]),
        triangles=np.concatenate([triangles, patch_triangles + len(vertices)]).astype(np.int64),
        inferred=np.concatenate([np.zeros(len(vertices), bool), np.ones(len(patch_vertices), bool)]),
    )


def _segments_enter_box(origin: np.ndarray, points: np.ndarray, node: SceneNode) -> np.ndarray:
    """Whether the straight line from origin to each point passes through the node's box.

    The slab test in the box's own frame: the line is inside the box for the
    parameters where it is inside all three pairs of faces at once.
    """
    matrix = np.asarray(node.transform.m, dtype=np.float64).reshape(4, 4)
    half = np.array([node.dimensions.x, node.dimensions.y, node.dimensions.z]) / 2
    start = (origin - matrix[:3, 3]) @ matrix[:3, :3]
    direction = (points - matrix[:3, 3]) @ matrix[:3, :3] - start
    parallel = np.abs(direction) < SEGMENT_EPSILON
    safe = np.where(parallel, SEGMENT_EPSILON, direction)
    first, second = (-half - start) / safe, (half - start) / safe
    enter = np.where(parallel, -np.inf, np.minimum(first, second)).max(axis=1)
    leave = np.where(parallel, np.inf, np.maximum(first, second)).min(axis=1)
    outside_a_slab = (parallel & (np.abs(start) > half)).any(axis=1)
    return ~outside_a_slab & (enter <= leave) & (leave > 0.0) & (enter < 1.0)


def hidden_behind_objects(graph: SceneGraph, vertices: np.ndarray, patches: np.ndarray):
    """For each camera, the patch vertices a measured object stands between it and.

    The LiDAR often misses the legs and underside of a chair as well as the floor
    beneath it, so no scanned surface blocks the view, and the floor patch there
    would take the chair's colour from every photo. The object's measured box is
    in the graph even where its surface is not in the scan, so it does the blocking.
    """
    objects = [
        node for node in graph.nodes
        if not (bounds_the_room(node) and node.parent_id is None) and node.relation != "cut_into"
    ]
    patch_index = np.flatnonzero(patches)

    def hidden(camera) -> np.ndarray:
        blocked = np.zeros(len(vertices), dtype=bool)
        for node in objects:
            blocked[patch_index] |= _segments_enter_box(camera.position, vertices[patch_index], node)
        return blocked

    return hidden
