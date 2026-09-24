"""Baking photographs into an atlas over the painted scan."""

from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace

import numpy as np
import pytest
from standardphysics_pipeline.check_blender import blender_path
from standardphysics_pipeline.coords import capture_to_room
from standardphysics_pipeline.ingest import parse_room_json
from standardphysics_pipeline.textures.hole_patches import with_holes_patched
from standardphysics_pipeline.textures.project import face_normals
from standardphysics_pipeline.textures.scan_atlas import (
    TEXEL_METRES,
    _face_filled,
    agreed_colours,
    atlas_size,
    unwrapped,
)
from standardphysics_pipeline.textures.scan_colour import SEEN_TOLERANCE, ColouredScan, _seen_tolerance, scan_geometry

REPO = pathlib.Path(__file__).resolve().parents[3]


def _blender_missing() -> bool:
    try:
        blender_path()
    except (FileNotFoundError, RuntimeError):
        return True
    return False


@pytest.mark.skipif(_blender_missing(), reason="Blender not installed")
def test_a_real_lidar_mesh_unwraps_to_texels_a_few_centimetres_across(tmp_path):
    vertices, triangles = scan_geometry(REPO / "datasets/phone/test1/lidar-mesh.json", capture_to_room(0.0))
    scan = ColouredScan(vertices, triangles, np.zeros((len(vertices), 3)), np.zeros(len(vertices), bool))

    mesh = unwrapped(scan, tmp_path, max_triangles=260_000)
    size = atlas_size(mesh)

    _, world_areas = face_normals(mesh.corners)
    first, second = mesh.uv[:, 1] - mesh.uv[:, 0], mesh.uv[:, 2] - mesh.uv[:, 0]
    texels = (np.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]) / 2).sum() * size ** 2
    assert np.sqrt(world_areas.sum() / texels) <= 1.5 * TEXEL_METRES


def test_one_photo_of_a_passer_by_loses_to_four_photos_of_the_floor():
    floor, person = np.array([0.30, 0.28, 0.25]), np.array([0.05, 0.05, 0.40])
    weights = np.array([[0.9, 0.5, 0.45, 0.4, 0.35]], dtype=np.float32)
    colours = np.array([[person, floor, floor + 0.01, floor - 0.01, floor]], dtype=np.float32)

    assert agreed_colours(weights, colours)[0] == pytest.approx(floor, abs=0.02)


def test_where_every_view_agrees_the_best_view_dominates():
    weights = np.array([[0.9, 0.3, 0.0, 0.0, 0.0]], dtype=np.float32)
    colours = np.array([[[0.50, 0.50, 0.50], [0.54, 0.54, 0.54], [0, 0, 0], [0, 0, 0], [0, 0, 0]]], dtype=np.float32)

    assert agreed_colours(weights, colours)[0] == pytest.approx([0.50, 0.50, 0.50], abs=0.005)


@pytest.mark.skipif(_blender_missing(), reason="Blender not installed")
def test_thinning_a_patched_scan_keeps_its_surface(tmp_path):
    """Hole patches arrive as separate squares; thinned unwelded, they broke into a lattice with gaps."""
    graph = parse_room_json(json.loads((REPO / "datasets/phone/test1/room.json").read_text()))
    vertices, triangles = scan_geometry(REPO / "datasets/phone/test1/lidar-mesh.json", graph.capture_to_room)
    patched = with_holes_patched(vertices, triangles, graph)
    scan = ColouredScan(patched.vertices, patched.triangles, np.zeros((len(patched.vertices), 3)), np.zeros(len(patched.vertices), bool))
    _, before = face_normals(patched.vertices[patched.triangles])

    mesh = unwrapped(scan, tmp_path, max_triangles=len(patched.triangles) // 9)
    _, after = face_normals(mesh.corners)

    assert after.sum() >= 0.97 * before.sum()


def test_a_surface_seen_at_a_slant_is_allowed_the_depth_it_spans_across_a_buffer_pixel():
    camera = SimpleNamespace(width=1600, fx=1100.0)
    depth, facing = np.array([4.0, 4.0]), np.array([1.0, 0.3])
    face_on, slanted = _seen_tolerance(camera, 240, depth, facing, slope_aware=True)
    assert face_on == pytest.approx(SEEN_TOLERANCE)
    assert slanted > 3 * SEEN_TOLERANCE
    assert _seen_tolerance(camera, 240, depth, facing, slope_aware=False) == SEEN_TOLERANCE


def test_a_texel_a_photo_missed_takes_its_face_colour_not_the_fallback():
    yellow, grey = [0.8, 0.6, 0.1], [0.5, 0.5, 0.5]
    surface = SimpleNamespace(faces=np.array([0, 0, 0, 1]), fallback=np.array([grey] * 4, dtype=np.float32))
    colours = np.array([yellow, yellow, [0, 0, 0], [0, 0, 0]], dtype=np.float32)
    painted = np.array([True, True, False, False])

    filled = _face_filled(surface, colours, painted)

    assert filled[2] == pytest.approx(yellow)
    assert filled[3] == pytest.approx(grey)
