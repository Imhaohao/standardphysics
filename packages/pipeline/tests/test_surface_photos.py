"""Photographic surface visibility: correct depth, occluders, and missing views."""
import numpy as np
import pytest

pytest.importorskip("numba", reason="offline photographic bake requires reconstruction extra")

from standardphysics_pipeline.textures.camera import PhotoCamera
from standardphysics_pipeline.textures.surface_photos import choose_views, surface_depth, visible_points


def camera():
    return PhotoCamera("frame-0000", np.eye(4), 50, 50, 31.5, 23.5, 64, 48, 0)


def square(z, half):
    return np.array([[-half, -half, z], [half, -half, z], [half, half, z], [-half, half, z]], dtype=float)


def test_foreground_triangle_interior_blocks_background_even_without_vertices_on_ray():
    front, back = square(2, .4), square(3, 1.2)
    faces = np.array([[0, 2, 1], [0, 3, 2]])
    buffer = surface_depth(camera(), np.vstack([front, back]), np.vstack([faces, faces+4]))
    visible, _, _ = visible_points(camera(), np.array([[0, 0, 2], [0, 0, 3], [.9, 0, 3]]), buffer)
    assert visible.tolist() == [True, False, True]


def test_sloping_surface_has_perspective_correct_depth_without_artificial_erosion():
    vertices = square(2, 2)
    vertices[:, 2] += vertices[:, 0]*.4
    faces = np.array([[0, 2, 1], [0, 3, 2]])
    cam = camera()
    buffer = surface_depth(cam, vertices, faces)
    # Intersect each pixel ray with z = 2 + 0.4*x.
    for column in [10, 30, 50]:
        expected = 2/(1-.4*(column-cam.cx)/cam.fx)
        assert buffer[24, column] == pytest.approx(expected, abs=1e-5)


def test_unobserved_surface_has_no_assigned_photograph():
    vertices = square(-2, .4)
    faces = np.array([[0, 2, 1], [0, 3, 2]])
    assignments, areas = choose_views(vertices, faces, [camera()])
    assert assignments.tolist() == [-1, -1]
    assert areas.sum() == pytest.approx(.64)


def test_matching_front_surface_can_receive_a_view():
    vertices = square(2, .4)
    faces = np.array([[0, 2, 1], [0, 3, 2]])
    assignments, _ = choose_views(vertices, faces, [camera()])
    assert assignments.tolist() == [0, 0]


def test_partially_occluded_face_receives_view_but_hidden_face_stays_unassigned():
    from standardphysics_pipeline.textures.surface_photos import choose_views_partial
    cam = camera()
    back = square(3, 1.2)
    front = square(2, .45) + np.array([[.75, 1.05, 0]])
    faces = np.array([[0, 2, 1], [0, 3, 2]])
    all_vertices = np.vstack([back, front])
    all_faces = np.vstack([faces, faces + 4])
    strict, _ = choose_views(back, faces, [cam], all_vertices, all_faces)
    partial, _ = choose_views_partial(back, faces, [cam], all_vertices, all_faces)
    assert strict.tolist() == [-1, -1]
    assert partial.tolist() == [0, 0]
    hidden = square(-2, .4)
    partial_hidden, _ = choose_views_partial(hidden, faces, [cam], hidden, faces)
    assert partial_hidden.tolist() == [-1, -1]


def test_partial_rule_without_centre_accepts_centre_hidden_but_spread_visible_and_rejects_big_occluder():
    from standardphysics_pipeline.textures.surface_photos import choose_views_partial
    cam = camera()
    back = square(3, 1.2)
    # occluder that hides only the centre sample band but leaves corners and mids visible
    centre_band = square(2, .18) + np.array([[0, 0, 0]])
    faces = np.array([[0, 2, 1], [0, 3, 2]])
    all_vertices = np.vstack([back, centre_band])
    all_faces = np.vstack([faces, faces + 4])
    assignment, _ = choose_views_partial(back, faces, [cam], all_vertices, all_faces, centre_required=False)
    assert assignment.tolist() == [0, 0]
    # a large close occluder in front hides most samples: face must stay neutral
    big = square(2.0, 1.4)
    assignment_big, _ = choose_views_partial(back, faces, [cam], np.vstack([back, big]), all_faces, centre_required=False)
    assert assignment_big.tolist() == [-1, -1]
