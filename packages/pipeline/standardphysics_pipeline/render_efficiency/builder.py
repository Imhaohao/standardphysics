"""Build deterministic surface Gaussians from the measured mesh and best-view colour.

Centres stay on the measured surface; normals come from measured triangles and
are rejected when degenerate.  Colour is interpolated from per-vertex best-view
colour (see ``textures.scan_colour``) rather than any learned head.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .metrics import MetricError
from .surface_splats import (
    SurfaceGaussians,
    inverse_sigmoid,
    sh0_from_rgb,
    surface_covariance,
)


def sample_mesh(
    vertices: np.ndarray,
    triangles: np.ndarray,
    spacing: float,
    seed: int = 1729,
    max_samples: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Area-weighted samples on the mesh, with owner triangle and face normal.

    Returns (points, normals, owners, barycentric_a, barycentric_b).  Degenerate
    triangles (``area <= 1e-10``) are skipped and their normals are never
    invented.
    """

    vertices = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(triangles, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3:
        raise MetricError(f"vertices must be Nx3, got {vertices.shape}")
    if triangles.ndim != 2 or triangles.shape[1] != 3:
        raise MetricError(f"triangles must be Tx3, got {triangles.shape}")

    corners = vertices[triangles]
    edge_1 = corners[:, 1] - corners[:, 0]
    edge_2 = corners[:, 2] - corners[:, 0]
    cross = np.cross(edge_1, edge_2)
    areas = np.linalg.norm(cross, axis=1) / 2.0
    valid = areas > 1e-10
    counts = np.where(valid, np.maximum(1, np.rint(areas / spacing**2)).astype(np.int64), 0)
    if not counts.any():
        raise MetricError("mesh has no non-degenerate triangles")

    owner = np.repeat(np.arange(len(triangles)), counts)
    generator = np.random.default_rng(seed)
    if max_samples is not None and len(owner) > max_samples:
        chosen = generator.choice(len(owner), size=max_samples, replace=False)
        owner = owner[chosen]

    first = generator.random(len(owner))
    second = generator.random(len(owner))
    root = np.sqrt(first)
    bary_a = 1.0 - root
    bary_b = root * (1.0 - second)
    bary_c = root * second
    corners = vertices[triangles[owner]]
    points = bary_a[:, None] * corners[:, 0] + bary_b[:, None] * corners[:, 1] + bary_c[:, None] * corners[:, 2]

    normals = cross[owner] / np.maximum(np.linalg.norm(cross[owner], axis=1, keepdims=True), 1e-12)
    return (
        points.astype(np.float32),
        normals.astype(np.float32),
        owner.astype(np.int64),
        bary_a.astype(np.float32),
        bary_b.astype(np.float32),
    )


@dataclass(frozen=True)
class BuildResult:
    gaussians: SurfaceGaussians
    supported_count: int
    rejected_count: int


def build_surface_gaussians(
    vertices: np.ndarray,
    triangles: np.ndarray,
    vertex_colours: np.ndarray,
    spacing: float,
    tangent_factor: float = 0.75,
    normal_ratio: float = 0.1,
    opacity: float = 0.5,
    seed: int = 1729,
    max_samples: int | None = 150000,
) -> BuildResult:
    """Sample the mesh, reject degenerate normals, and build bounded Gaussians.

    ``vertex_colours`` must be Nx3 in [0,1].  Samples on degenerate faces are
    excluded up front, then any remaining non-finite normal/colour is rejected
    and reported rather than presented as measured geometry.
    """
    vertices = np.asarray(vertices, dtype=np.float64)
    vertex_colours = np.asarray(vertex_colours, dtype=np.float64)
    if vertex_colours.shape != (len(vertices), 3):
        raise MetricError(f"vertex_colours must be Nx3 matching vertices, got {vertex_colours.shape}")
    if not 0.0 < opacity < 1.0:
        raise MetricError(f"opacity must be in (0,1), got {opacity}")

    points, normals, owners, bary_a, bary_b = sample_mesh(
        vertices, triangles, spacing, seed=seed, max_samples=max_samples
    )
    corners = vertices[triangles[owners]]
    bary_c = 1.0 - bary_a - bary_b
    colours = (
        bary_a[:, None] * corners[:, 0]
        + bary_b[:, None] * corners[:, 1]
        + bary_c[:, None] * corners[:, 2]
    )

    finite = np.isfinite(points).all(axis=1) & np.isfinite(normals).all(axis=1) & np.isfinite(colours).all(axis=1)
    norm_finite = (np.linalg.norm(normals, axis=1) > 0.5) & finite
    points, normals, colours = points[norm_finite], normals[norm_finite], colours[norm_finite]
    rejected = int((~norm_finite).sum())

    if len(points) == 0:
        raise MetricError("no supported, non-degenerate surface samples remain")

    frames, scales = surface_covariance(normals, spacing, tangent_factor, normal_ratio)
    sh0 = sh0_from_rgb(np.clip(colours, 0.0, 1.0))
    opacities = np.full(len(points), opacity, dtype=np.float32)
    gaussians = SurfaceGaussians(
        positions=points,
        frames=frames,
        scales=scales,
        opacities=opacities,
        sh0=sh0,
        geometry_only=False,
    )
    return BuildResult(gaussians=gaussians, supported_count=len(points), rejected_count=rejected)


__all__ = ["BuildResult", "build_surface_gaussians", "inverse_sigmoid", "sample_mesh", "sh0_from_rgb"]
