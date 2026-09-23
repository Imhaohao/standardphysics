"""Baking photographs into an atlas over the painted scan."""

from __future__ import annotations

import pathlib

import numpy as np
import pytest
from standardphysics_pipeline.check_blender import blender_path
from standardphysics_pipeline.coords import capture_to_room
from standardphysics_pipeline.textures.project import face_normals
from standardphysics_pipeline.textures.scan_atlas import TEXEL_METRES, agreed_colours, atlas_size, unwrapped
from standardphysics_pipeline.textures.scan_colour import ColouredScan, scan_geometry

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
