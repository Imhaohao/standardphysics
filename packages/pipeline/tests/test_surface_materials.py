"""Filling unphotographed walls and floors with a generated material.

The room is a four metre floor with one wall standing on its far edge, both as
real measured sheets, so which vertex belongs to which surface is geometry.
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest
from standardphysics_contracts import Mat4, SceneGraph, SceneNode, Vec3
from standardphysics_pipeline.textures.project import to_linear
from standardphysics_pipeline.textures.scan_colour import ColouredScan, vertex_normals
from standardphysics_pipeline.textures.surface_materials import (
    SURFACE_KINDS,
    SurfaceMaterial,
    load_materials,
    planar_sample,
    room_surfaces,
    unseen_surfaces_filled,
)

WALL, FLOOR = SURFACE_KINDS.index("wall"), SURFACE_KINDS.index("floor")


def sheet(label: str, size: tuple[float, float, float], at: tuple[float, float, float]) -> SceneNode:
    return SceneNode(
        id=uuid.uuid4(), kind=label.lower(), label=label, raw_category=label.lower(),
        dimensions=Vec3(x=size[0], y=size[1], z=size[2]), transform=Mat4.translation(*at),
    )


def room() -> SceneGraph:
    return SceneGraph(scan_id=uuid.uuid4(), nodes=[
        sheet("Wall", (4.0, 0.0, 3.0), (0.0, 2.0, 1.5)),
        sheet("Floor", (4.0, 4.0, 0.0), (0.0, 0.0, 0.0)),
    ])


def patch(origin, across, up, steps: int = 6) -> tuple[np.ndarray, np.ndarray]:
    """A grid of vertices facing along across x up, triangulated so the normals agree."""
    origin, across, up = (np.asarray(value, dtype=float) for value in (origin, across, up))
    grid = np.array([origin + across * i / steps + up * j / steps for j in range(steps + 1) for i in range(steps + 1)])
    row = steps + 1
    triangles = []
    for j in range(steps):
        for i in range(steps):
            corner = j * row + i
            triangles += [[corner, corner + 1, corner + row + 1], [corner, corner + row + 1, corner + row]]
    return grid, np.asarray(triangles)


def joined(*patches) -> tuple[np.ndarray, np.ndarray]:
    vertices, triangles, offset = [], [], 0
    for grid, faces in patches:
        vertices.append(grid)
        triangles.append(faces + offset)
        offset += len(grid)
    return np.concatenate(vertices), np.concatenate(triangles)


def wall_patch():
    return patch((-1.0, 1.98, 0.5), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), steps=12)


def floor_patch():
    return patch((-1.0, -1.0, 0.01), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


def flat_material(value: float = 0.5) -> SurfaceMaterial:
    return SurfaceMaterial(np.full((8, 8, 3), value, dtype=np.float32), metres_across=1.0)


def classified(vertices, triangles):
    return room_surfaces(vertices, vertex_normals(vertices, triangles), room())


def test_wall_and_floor_vertices_are_told_apart():
    vertices, triangles = joined(wall_patch(), floor_patch())
    surfaces = classified(vertices, triangles)
    wall_count = len(wall_patch()[0])
    assert (surfaces.kinds[:wall_count] == WALL).all()
    assert (surfaces.kinds[wall_count:] == FLOOR).all()


def test_a_shelf_top_inside_the_wall_box_is_not_the_wall():
    vertices, triangles = patch((-1.0, 1.9, 1.2), (1.0, 0.0, 0.0), (0.0, 0.08, 0.0))
    assert (classified(vertices, triangles).kinds == -1).all()


def test_the_underside_of_something_on_the_floor_is_not_the_floor():
    vertices, triangles = patch((-1.0, -1.0, 0.05), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
    assert (classified(vertices, triangles).kinds == -1).all()


def test_things_away_from_every_sheet_are_left_alone():
    vertices, triangles = patch((-0.5, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    assert (classified(vertices, triangles).kinds == -1).all()


def half_seen_wall(photo_colour: float = 0.7) -> ColouredScan:
    vertices, triangles = wall_patch()
    seen = vertices[:, 0] < 0.0
    colours = np.where(seen[:, None], photo_colour, 0.62).astype(np.float32)
    return ColouredScan(vertices, triangles, np.broadcast_to(colours, (len(vertices), 3)).copy(), seen)


def test_the_fill_takes_the_photographed_colour_of_its_own_wall():
    scan = half_seen_wall(photo_colour=0.7)
    filled = unseen_surfaces_filled(scan, room(), {"wall": flat_material()})
    np.testing.assert_allclose(filled.colours[~scan.seen], 0.7, atol=1e-3)


def test_photographed_vertices_and_coverage_are_never_changed():
    scan = half_seen_wall()
    filled = unseen_surfaces_filled(scan, room(), {"wall": flat_material(0.2)})
    np.testing.assert_array_equal(filled.colours[scan.seen], scan.colours[scan.seen])
    np.testing.assert_array_equal(filled.seen, scan.seen)
    assert filled.painted_fraction == scan.painted_fraction


def test_without_materials_the_scan_is_returned_unchanged():
    scan = half_seen_wall()
    assert unseen_surfaces_filled(scan, room(), {}) is scan


def test_the_pattern_repeats_at_its_real_size():
    tile = np.random.default_rng(3).random((16, 16, 3)).astype(np.float32)
    material = SurfaceMaterial(tile, metres_across=0.5)
    facing_wall = np.tile([0.0, -1.0, 0.0], (2, 1))
    points = np.array([[0.13, 2.0, 1.07], [0.63, 2.0, 1.57]])
    first, second = planar_sample(material, points, facing_wall)
    np.testing.assert_allclose(first, second, atol=1e-5)


def test_a_missing_manifest_means_no_materials(tmp_path):
    assert load_materials(tmp_path) == {}


@pytest.mark.parametrize("kind", SURFACE_KINDS)
def test_the_shipped_tiles_load_as_linear_colour(kind):
    material = load_materials()[kind]
    assert material.tile.ndim == 3 and material.tile.shape[2] == 3
    assert material.metres_across > 0
    assert 0.0 < float(material.tile.mean()) < float(to_linear(np.array(1.0)))
