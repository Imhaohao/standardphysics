"""Thinning the scan before Blender unwraps it keeps the surface where the LiDAR measured it.

Blender used to thin the scan itself, and on a two-core server a library floor
of four million faces ran it out of memory. The mesh is now thinned part of the
way first, so these check that thinning against a room really scanned, not a
shape made to pass.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest
from scipy.spatial import cKDTree
from standardphysics_pipeline.ingest import parse_room_json
from standardphysics_pipeline.textures.hole_patches import with_holes_patched
from standardphysics_pipeline.textures.project import face_normals
from standardphysics_pipeline.textures.scan_atlas import thinned_for_blender, welded
from standardphysics_pipeline.textures.scan_colour import scan_geometry

REPO = pathlib.Path(__file__).resolve().parents[3]
SAMPLES_PER_FACE = 60


@pytest.fixture(scope="module")
def patched_scan():
    graph = parse_room_json(json.loads((REPO / "datasets/phone/test1/room.json").read_text()))
    vertices, triangles = scan_geometry(REPO / "datasets/phone/test1/lidar-mesh.json", graph.capture_to_room)
    patched = with_holes_patched(vertices, triangles, graph)
    return patched.vertices, patched.triangles


def _surface_samples(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Points spread over every face, so a distance to them is a distance to the surface within a few millimetres."""
    weights = np.random.default_rng(0).dirichlet(np.ones(3), SAMPLES_PER_FACE)
    corners = vertices[triangles]
    return np.concatenate([corners.reshape(-1, 3), np.einsum("sk,fkd->fsd", weights, corners).reshape(-1, 3)])


def _rim(faces: np.ndarray) -> np.ndarray:
    edges = np.sort(faces[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    return np.unique(unique[counts == 1].ravel())


def test_thinning_by_a_quarter_keeps_the_surface_within_a_centimetre(patched_scan):
    """A quarter is harsher than the pass a library floor gets, four million faces down to Blender's million and a half."""
    vertices, triangles = patched_scan
    points, faces = welded(vertices, triangles)
    target = len(triangles) // 4

    thinned_points, thinned_faces = thinned_for_blender(vertices, triangles, target)

    assert len(thinned_faces) <= target
    distances, _ = cKDTree(_surface_samples(thinned_points, thinned_faces)).query(points)
    assert np.percentile(distances, 95) < 0.015
    _, before = face_normals(points[faces])
    _, after = face_normals(thinned_points[thinned_faces])
    assert after.sum() >= 0.97 * before.sum()


def test_the_rim_of_every_hole_stays_where_it_was_measured(patched_scan):
    """Quadric thinning drags a hole's rim inward, so rims are left for Blender to thin."""
    vertices, triangles = patched_scan
    points, faces = welded(vertices, triangles)

    thinned_points, _ = thinned_for_blender(vertices, triangles, len(triangles) // 4)

    moved, _ = cKDTree(thinned_points).query(points[_rim(faces)])
    assert len(_rim(faces)) > 0.1 * len(points)
    assert moved.max() < 1e-6


def test_welding_joins_the_patch_squares_and_anchor_seams(patched_scan):
    """Patch squares share corners as separate vertices; unjoined, each square thins on its own into a lattice."""
    vertices, triangles = patched_scan

    points, faces = welded(vertices, triangles)

    assert len(points) < len(np.unique(triangles))
    assert len(faces) <= len(triangles)
    assert len(cKDTree(points).query_pairs(0.0005)) == 0


def test_a_mesh_already_small_enough_is_only_welded(patched_scan):
    vertices, triangles = patched_scan

    points, faces = thinned_for_blender(vertices, triangles, len(triangles) * 2)

    assert np.array_equal(faces, welded(vertices, triangles)[1])
    assert len(points) == len(np.unique(faces))
