"""Renderer/camera correctness tests (policy R01).

The repaired camera pipeline (allowlist.camera_from_transforms ->
PhotoCamera.project) must agree with an independently written pinhole
reference to within 0.25 px on an asymmetric scene with off-centre
intrinsics, and each axis flip/transpose/mirror/negation corruption must move
control-point projections far beyond 0.25 px (so the test detects them).
"""

from __future__ import annotations

import numpy as np
import pytest
from standardphysics_pipeline.render_efficiency.allowlist import camera_from_transforms

OFF_CENTRE_FRAME = {
    "file_path": "images/asymmetric.jpg",
    "transform_matrix": (
        [[0.652, -0.758, -0.006, -2.1],
         [0.634, 0.550, -0.543, 1.7],
         [0.415, 0.350, 0.840, 2.9],
         [0.0, 0.0, 0.0, 1.0]]
    ),
    "fl_x": 903.25, "fl_y": 911.5, "cx": 275.0, "cy": 690.0,
    "w": 1280, "h": 960,
}

CONTROL_POINTS = np.array([
    [-0.9, 0.4, 0.2],
    [0.7, -0.3, 1.8],
    [0.1, 0.9, -0.7],
    [1.4, 0.5, 0.3],
    [-0.4, -0.8, 1.1],
])


def _reference_projection(matrix: np.ndarray, points: np.ndarray, fx: float, fy: float, cx: float, cy: float) -> np.ndarray:
    """Independent pinhole reference for the documented convention.

    The prepared frame matrix is camera-to-world; the pixel camera is
    world -> diag(1,-1,-1) @ world-to-camera with +X right, +Y down, +Z
    forward.  Written from the convention, without the pipeline helpers.
    """
    c2w = np.asarray(matrix, dtype=np.float64)
    r_inv = np.linalg.inv(c2w[:3, :3])
    t_inv = -r_inv @ c2w[:3, 3]
    flip = np.diag([1.0, -1.0, -1.0])
    rotation = flip @ r_inv
    translation = flip @ t_inv
    results = []
    for point in points:
        x = 0.0
        y = 0.0
        z = 0.0
        for axis in range(3):
            x += rotation[0, axis] * point[axis]
            y += rotation[1, axis] * point[axis]
            z += rotation[2, axis] * point[axis]
        x += translation[0]
        y += translation[1]
        z += translation[2]
        results.append([fx * x / z + cx, fy * y / z + cy])
    return np.asarray(results)


def _camera_from_matrix(matrix) -> object:
    frame = {
        **OFF_CENTRE_FRAME,
        "transform_matrix": matrix,
    }
    return camera_from_transforms(frame), frame


def test_r01_asymmetric_offcentre_projection_agrees_within_025px():
    camera, frame = _camera_from_matrix(OFF_CENTRE_FRAME["transform_matrix"])
    pipeline = np.stack(camera.project(CONTROL_POINTS)[:2], axis=1)
    reference = _reference_projection(
        np.asarray(frame["transform_matrix"], dtype=np.float64),
        CONTROL_POINTS,
        float(frame["fl_x"]), float(frame["fl_y"]), float(frame["cx"]), float(frame["cy"]),
    )
    error = np.linalg.norm(pipeline - reference, axis=1)
    assert float(error.max()) <= 0.25


def test_r01_flip_y_is_detected():
    _assert_corruption_detected("flip_y", row=1)


def test_r01_flip_x_is_detected():
    _assert_corruption_detected("flip_x", row=0)


def test_r01_transpose_is_detected():
    matrix = np.asarray(OFF_CENTRE_FRAME["transform_matrix"], dtype=np.float64)
    matrix[:3, :3] = matrix[:3, :3].T
    _assert_corruption_detected("transpose", matrix=matrix)


def test_r01_mirror_xy_is_detected():
    matrix = np.asarray(OFF_CENTRE_FRAME["transform_matrix"], dtype=np.float64)
    matrix[:3, :3] = matrix[:3, :3][[1, 0, 2]]
    _assert_corruption_detected("mirror_xy", matrix=matrix)


def test_r01_negate_forward_is_detected():
    _assert_corruption_detected("negate_forward", row=2)


def _assert_corruption_detected(name: str, row: int | None = None, matrix: list | None = None) -> None:
    baseline, _ = _camera_from_matrix(OFF_CENTRE_FRAME["transform_matrix"])
    baseline_px = np.stack(baseline.project(CONTROL_POINTS)[:2], axis=1)
    if matrix is None:
        corrupted = np.asarray(OFF_CENTRE_FRAME["transform_matrix"], dtype=np.float64)
        if row is not None:
            corrupted[row] *= -1.0
    else:
        corrupted = np.asarray(matrix, dtype=np.float64)
    bad_camera, _ = _camera_from_matrix(corrupted.tolist())
    bad_px = np.stack(bad_camera.project(CONTROL_POINTS)[:2], axis=1)
    shift = np.linalg.norm(bad_px - baseline_px, axis=1)
    assert shift.max() > 0.25, f"{name} corruption moved no control point beyond 0.25 px"


def test_r01_pipeline_roundtrips_calibrated_intrinsics():
    camera, frame = _camera_from_matrix(OFF_CENTRE_FRAME["transform_matrix"])
    assert camera.width == 1280 and camera.height == 960
    assert camera.fx == pytest.approx(frame["fl_x"])
    assert camera.fy == pytest.approx(frame["fl_y"])
