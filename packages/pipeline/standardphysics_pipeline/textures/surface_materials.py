"""Generated materials for the stretches of wall and floor no photo reached.

A scanned vertex no camera saw used to stay the scan's neutral grey, so a wall
read as photo patches floating on blank sheet. Here each of those vertices on a
room surface takes a repeating material instead, sampled at its real position
so the pattern keeps its physical size, and tinted to the median colour the
photos did record on that same surface so the fill meets the photo without a
step in brightness.

Display only. `seen` is never touched: a filled vertex is a picture of what the
surface probably looks like, and coverage keeps reporting what a camera measured.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
from PIL import Image
from standardphysics_contracts import SceneGraph, SceneNode, bounds_the_room, stands_upright

from .project import to_linear, to_srgb
from .scan_colour import ColouredScan, vertex_normals

SurfaceKind = Literal["wall", "floor"]
SURFACE_KINDS: tuple[SurfaceKind, ...] = ("wall", "floor")
MATERIALS_DIR = pathlib.Path(__file__).parent / "materials"
MANIFEST = "materials.json"

SURFACE_REACH = 0.10
"""How far off a measured sheet, in metres, a scanned vertex may sit and still belong to it."""
FACING_THE_SHEET = 0.8
"""How nearly a vertex must face along the sheet's normal to belong to it."""
MIN_SEEN_FOR_TINT = 50
"""Photographed vertices a surface needs before its own colour sets the tint."""


@dataclass(frozen=True)
class SurfaceMaterial:
    tile: np.ndarray
    """Linear RGB, float32, height x width x 3, repeating seamlessly in both directions."""
    metres_across: float
    """The real width one repetition of the tile covers."""


@dataclass(frozen=True)
class RoomSurfaces:
    kinds: np.ndarray
    """Index into SURFACE_KINDS per vertex, or -1 for anything that is not a room surface."""
    owners: np.ndarray
    """Index of the graph node each vertex belongs to, or -1."""


def load_materials(directory: pathlib.Path = MATERIALS_DIR) -> dict[SurfaceKind, SurfaceMaterial]:
    """The generated tiles, keyed by surface. No manifest means no materials, not an error."""
    manifest_path = directory / MANIFEST
    if not manifest_path.is_file():
        return {}
    manifest = json.loads(manifest_path.read_text())
    materials: dict[SurfaceKind, SurfaceMaterial] = {}
    for kind in SURFACE_KINDS:
        entry = manifest.get(kind)
        if entry is None:
            continue
        with Image.open(directory / entry["image"]) as opened:
            srgb = np.asarray(opened.convert("RGB"), dtype=np.float32) / 255.0
        materials[kind] = SurfaceMaterial(to_linear(srgb).astype(np.float32), float(entry["metres_across"]))
    return materials


def _is_room_sheet(node: SceneNode) -> bool:
    """A wall or floor; a door or window is cut into one and is not its own surface."""
    return bounds_the_room(node) and node.parent_id is None


def _node_frame(node: SceneNode) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    matrix = np.asarray(node.transform.m, dtype=np.float64).reshape(4, 4)
    half = np.array([node.dimensions.x, node.dimensions.y, node.dimensions.z]) / 2
    return matrix[:3, :3], matrix[:3, 3], half


def _vertices_on_sheet(node: SceneNode, vertices: np.ndarray, normals: np.ndarray) -> np.ndarray:
    """Vertices inside the sheet's padded box that face the room from it.

    A wall is seen from either side, so either facing counts. A floor is only
    ever its top: a vertex facing down inside a floor's box is the underside of
    something standing on it.
    """
    rotation, centre, half = _node_frame(node)
    local = (vertices - centre) @ rotation
    within = np.all(np.abs(local) <= half + SURFACE_REACH, axis=1)
    if stands_upright(node):
        sheet_normal = rotation[:, int(np.argmin(half))]
        return within & (np.abs(normals @ sheet_normal) >= FACING_THE_SHEET)
    return within & (normals[:, 2] >= FACING_THE_SHEET)


def room_surfaces(vertices: np.ndarray, normals: np.ndarray, graph: SceneGraph) -> RoomSurfaces:
    """Which measured wall or floor each scanned vertex lies on.

    The graph and the scan share the room frame, Z up. A vertex belongs to a
    sheet when it sits inside the sheet's box, padded because a wall is measured
    as a plane of no thickness, and faces along the sheet's normal, so the side
    of a cabinet pressed against a wall is not taken for the wall. Room graphs
    carry no ceiling, so a ceiling is left to whatever fills the rest.
    """
    kinds = np.full(len(vertices), -1, dtype=np.int8)
    owners = np.full(len(vertices), -1, dtype=np.int32)
    for index, node in enumerate(graph.nodes):
        if not _is_room_sheet(node):
            continue
        claimed = _vertices_on_sheet(node, vertices, normals) & (owners < 0)
        owners[claimed] = index
        kinds[claimed] = SURFACE_KINDS.index("wall" if stands_upright(node) else "floor")
    return RoomSurfaces(kinds, owners)


def _wrapped_bilinear(tile: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    height, width = tile.shape[:2]
    x, y = np.mod(u, width), np.mod(v, height)
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    x1, y1 = (x0 + 1) % width, (y0 + 1) % height
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    top = tile[y0, x0] * (1 - fx) + tile[y0, x1] * fx
    bottom = tile[y1, x0] * (1 - fx) + tile[y1, x1] * fx
    return top * (1 - fy) + bottom * fy


def planar_sample(material: SurfaceMaterial, positions: np.ndarray, normals: np.ndarray) -> np.ndarray:
    """The tile laid flat across whichever room axis each point faces, in linear RGB.

    Walls take the tile across their horizontal run and up their height, and
    floors across X and Y, so a floorboard is the same size wherever it lands.
    """
    facing_axis = np.argmax(np.abs(normals), axis=1)
    across = np.where(facing_axis == 0, positions[:, 1], positions[:, 0])
    along = np.where(facing_axis == 2, positions[:, 1], positions[:, 2])
    pixels_per_metre = material.tile.shape[1] / material.metres_across
    return _wrapped_bilinear(material.tile, across * pixels_per_metre, -along * pixels_per_metre)


def tinted_to(pattern: np.ndarray, target: np.ndarray, pattern_median: np.ndarray) -> np.ndarray:
    """The pattern with its median moved onto the target colour, keeping its texture."""
    return np.clip(pattern * (target / np.maximum(pattern_median, 1e-4)), 0.0, 1.0)


def _median_linear(colours_srgb: np.ndarray) -> np.ndarray | None:
    if len(colours_srgb) < MIN_SEEN_FOR_TINT:
        return None
    return np.median(to_linear(colours_srgb), axis=0)


def _tint_targets(scan: ColouredScan, surfaces: RoomSurfaces, kind_index: int) -> dict[int, np.ndarray]:
    """The photographed colour of each sheet of this kind, falling back to the room's for that kind."""
    of_kind = surfaces.kinds == kind_index
    room_colour = _median_linear(scan.colours[of_kind & scan.seen])
    targets = {}
    for owner in np.unique(surfaces.owners[of_kind]):
        own_colour = _median_linear(scan.colours[of_kind & scan.seen & (surfaces.owners == owner)])
        chosen = own_colour if own_colour is not None else room_colour
        if chosen is not None:
            targets[int(owner)] = chosen
    return targets


def _fill_kind(
    scan: ColouredScan, normals: np.ndarray, surfaces: RoomSurfaces,
    kind_index: int, material: SurfaceMaterial, colours: np.ndarray,
) -> None:
    unseen = (surfaces.kinds == kind_index) & ~scan.seen
    if not unseen.any():
        return
    pattern_median = np.median(material.tile.reshape(-1, 3), axis=0)
    targets = _tint_targets(scan, surfaces, kind_index)
    for owner in np.unique(surfaces.owners[unseen]):
        here = np.flatnonzero(unseen & (surfaces.owners == owner))
        pattern = planar_sample(material, scan.vertices[here], normals[here])
        target = targets.get(int(owner), pattern_median)
        colours[here] = to_srgb(tinted_to(pattern, target, pattern_median))


def unseen_surfaces_filled(
    scan: ColouredScan, graph: SceneGraph, materials: dict[SurfaceKind, SurfaceMaterial]
) -> ColouredScan:
    """The scan with every unphotographed wall and floor vertex given its material."""
    if not materials or scan.seen.all():
        return scan
    normals = vertex_normals(scan.vertices, scan.triangles)
    surfaces = room_surfaces(scan.vertices, normals, graph)
    colours = scan.colours.copy()
    for kind_index, kind in enumerate(SURFACE_KINDS):
        material = materials.get(kind)
        if material is not None:
            _fill_kind(scan, normals, surfaces, kind_index, material, colours)
    return replace(scan, colours=colours)
