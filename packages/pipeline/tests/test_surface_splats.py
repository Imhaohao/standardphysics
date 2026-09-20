"""Synthetic fixtures for the deterministic surface-Gaussian builder."""

from __future__ import annotations

import numpy as np
import pytest
from standardphysics_pipeline.render_efficiency import (
    MetricError,
    SurfaceGaussians,
    build_surface_gaussians,
    inverse_sigmoid,
    quaternion_from_rotation,
    rgb_from_sh0,
    sh0_from_rgb,
    surface_covariance,
    tangent_basis,
)


def _grid_plane(side: int = 8, z: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = np.meshgrid(np.arange(side, dtype=np.float64), np.arange(side, dtype=np.float64))
    vertices = np.stack([xs.ravel(), ys.ravel(), np.full(side * side, z)], axis=1)
    triangles = []
    for r in range(side - 1):
        for c in range(side - 1):
            i = r * side + c
            triangles.append([i, i + side, i + 1])
            triangles.append([i + 1, i + side, i + side + 1])
    return vertices, np.asarray(triangles, dtype=np.int64)


def test_sh0_roundtrip():
    rgb = np.array([[1.0, 0.5, 0.25], [0.1, 0.2, 0.3]])
    assert np.allclose(rgb_from_sh0(sh0_from_rgb(rgb)), rgb, atol=1e-5)


def test_sh0_known_zero_rgb():
    f_dc = sh0_from_rgb(np.zeros(3))
    # (0 - 0.5) / 0.28209479177387814
    expected = -0.5 / 0.28209479177387814
    assert np.allclose(f_dc, expected)


def test_sh0_rejects_bad_shape():
    with pytest.raises(MetricError):
        sh0_from_rgb(np.zeros((2, 2)))


def test_tangent_basis_plus_z():
    t1, t2 = tangent_basis(np.array([0.0, 0.0, 1.0]))
    assert np.allclose(np.linalg.norm(t1), 1.0)
    assert np.allclose(np.linalg.norm(t2), 1.0)
    assert np.allclose(np.dot(t1, t2), 0.0, atol=1e-6)
    assert np.allclose(t2, [0.0, 0.0, 1.0]) or np.allclose(np.cross(t1, t2), [0.0, 0.0, 1.0])


def test_tangent_basis_minus_z():
    t1, t2 = tangent_basis(np.array([0.0, 0.0, -1.0]))
    assert np.allclose(np.linalg.norm(t1), 1.0)
    assert np.allclose(np.linalg.norm(t2), 1.0)
    assert np.allclose(np.dot(t1, t2), 0.0, atol=1e-6)


def test_tangent_basis_orthonormal_set():
    oblique = np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0)
    normals = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], oblique, [0.0, 0.0, -1.0]])
    t1, t2 = tangent_basis(normals)
    for row in range(4):
        assert t1[row].dot(t2[row]) == pytest.approx(0.0, abs=1e-6)
        assert np.linalg.norm(t1[row]) == pytest.approx(1.0, abs=1e-6)
        assert np.linalg.norm(t2[row]) == pytest.approx(1.0, abs=1e-6)
        # [t1, t2, n] right-handed
        assert np.linalg.det(np.stack([t1[row], t2[row], normals[row]], axis=1)) == pytest.approx(1.0, abs=1e-4)


def test_covariance_normal_is_smallest_axis():
    normal = np.array([0.0, 0.0, 1.0])
    frames, scales = surface_covariance(normal, spacing_h=0.05, tangent_factor=0.75, normal_ratio=0.1)
    rotation = frames  # 3x3, columns = [t1, t2, n]
    covariance = rotation @ np.diag(scales**2) @ rotation.T
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    assert np.allclose(eigenvectors[:, 0], [0.0, 0.0, 1.0], atol=1e-4) or np.allclose(
        eigenvectors[:, 0], [0.0, 0.0, -1.0], atol=1e-4
    )
    assert eigenvalues[0] == pytest.approx((0.75 * 0.05 * 0.1) ** 2, rel=1e-4)


def test_covariance_rejects_bad_inputs():
    with pytest.raises(MetricError):
        surface_covariance(np.array([0.0, 0.0, 1.0]), spacing_h=0.0)
    with pytest.raises(MetricError):
        surface_covariance(np.array([0.0, 0.0, 1.0]), spacing_h=-0.05)
    with pytest.raises(MetricError):
        surface_covariance(np.array([0.0, 0.0, 1.0]), spacing_h=0.05, normal_ratio=1.5)


def test_quaternion_identity():
    identity = np.eye(3)
    quat = quaternion_from_rotation(identity)
    assert np.allclose(quat, [1.0, 0.0, 0.0, 0.0], atol=1e-6)
    assert np.linalg.norm(quat) == pytest.approx(1.0)


def test_quaternion_90_degree_z():
    angle = np.pi / 2
    rotation = np.array([
        [np.cos(angle), -np.sin(angle), 0.0],
        [np.sin(angle), np.cos(angle), 0.0],
        [0.0, 0.0, 1.0],
    ])
    quat = quaternion_from_rotation(rotation)
    assert np.allclose(quat, [np.cos(angle / 2), 0.0, 0.0, np.sin(angle / 2)], atol=1e-6)


def test_inverse_sigmoid_roundtrip():
    for value in (0.1, 0.5, 0.9):
        logit = inverse_sigmoid(np.array(value))
        recovered = 1.0 / (1.0 + np.exp(-logit))
        assert recovered == pytest.approx(value, abs=1e-6)


def test_builder_caps_sample_count():
    vertices, triangles = _grid_plane(side=32)
    colours = np.full((len(vertices), 3), 0.5)
    result = build_surface_gaussians(
        vertices, triangles, colours, spacing=0.1, max_samples=500, seed=1729
    )
    assert len(result.gaussians) <= 500


def test_builder_interpolates_vertex_colours():
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
    triangles = np.array([[0, 1, 2]], dtype=np.int64)
    colours = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    result = build_surface_gaussians(vertices, triangles, colours, spacing=10.0, seed=1729)
    # A single sample inside the triangle blends the three pure corner colours,
    # so none of the RGB channels can be exactly 1.0 or 0.0 together.
    rgb = rgb_from_sh0(result.gaussians.sh0)
    assert (rgb < 1.0).all()
    assert (rgb > -1e-6).all()


def test_builder_skips_degenerate_triangle():
    vertices = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float64)
    triangles = np.array([[0, 1, 2]], dtype=np.int64)
    colours = np.zeros((3, 3))
    with pytest.raises(MetricError):
        build_surface_gaussians(vertices, triangles, colours, spacing=0.1)


def test_export_ply_then_read_header(tmp_path):
    silhouette = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    triangoli = np.array([[0, 1, 2]])
    colours = np.full((3, 3), 0.5)
    result = build_surface_gaussians(silhouette, triangoli, colours, spacing=10.0)
    out = tmp_path / "surface.ply"
    result.gaussians.export_ply(out)
    raw = out.read_bytes()
    assert raw.startswith(b"ply\n")
    assert f"element vertex {len(result.gaussians)}".encode() in raw


def test_export_rejects_nonfinite():
    gauss = SurfaceGaussians(
        positions=np.array([[np.nan, 0.0, 0.0]]),
        frames=np.eye(3)[None],
        scales=np.array([[0.01, 0.01, 0.01]]),
        opacities=np.array([0.5]),
        sh0=np.array([[0.0, 0.0, 0.0]]),
    )
    with pytest.raises(MetricError):
        gauss.export_ply(__import__("pathlib").Path("unused.ply"))
