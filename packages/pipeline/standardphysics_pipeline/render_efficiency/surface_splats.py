"""Deterministic Gaussian primitives built on the measured surface.

This is the fixed surface-construction path: centres stay on the LiDAR mesh,
normals come from measured triangles (rejected when degenerate, never invented),
and covariance is a bounded tangent frame flattened along the normal.  There is
no learned head and no random-weight inference.  Geometry-only output is named
as such rather than presented as colour.

Colour is supplied separately (best-view photo sampling); this module owns the
geometry, the covariance, and the PLY export.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import numpy as np

from .metrics import MetricError

SH0_NORMALIZER = 0.28209479177387814
"""1 / sqrt(4 * pi); the SH0 coefficient for a unit RGB in the 3DGS convention."""


def sh0_from_rgb(rgb: np.ndarray) -> np.ndarray:
    """Encode linear/sRGB [0,1] RGB as the SH degree-0 coefficient f_dc."""
    rgb = np.asarray(rgb, dtype=np.float64)
    if rgb.ndim == 1:
        rgb = rgb[None, :]
    if rgb.shape[1] != 3:
        raise MetricError(f"RGB must be Nx3, got {rgb.shape}")
    return ((rgb - 0.5) / SH0_NORMALIZER).astype(np.float32)


def rgb_from_sh0(f_dc: np.ndarray) -> np.ndarray:
    """Inverse of :func:`sh0_from_rgb`, for roundtrip tests."""
    f_dc = np.asarray(f_dc, dtype=np.float64)
    return f_dc * SH0_NORMALIZER + 0.5


def inverse_sigmoid(opacity: np.ndarray) -> np.ndarray:
    """Opacity in [0,1] -> logit, clipped to finite bracket."""
    clipped = np.clip(np.asarray(opacity, dtype=np.float64), 1e-6, 1.0 - 1e-6)
    return np.log(clipped / (1.0 - clipped)).astype(np.float32)


def tangent_basis(normals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two orthonormal tangent vectors per normal, stable for +Z and -Z normals.

    Returns (t1, t2) each (N,3).  ``[t1, t2, n]`` is a right-handed frame.
    """
    normals = np.asarray(normals, dtype=np.float64)
    single = normals.ndim == 1
    if single:
        normals = normals[None, :]
    reference = np.where(
        np.abs(normals[:, 2])[:, None] > 0.9,
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 0.0, 1.0]),
    )
    tangent_1 = np.cross(reference, normals)
    tangent_1 /= np.maximum(np.linalg.norm(tangent_1, axis=1, keepdims=True), 1e-12)
    tangent_2 = np.cross(normals, tangent_1)
    tangent_2 /= np.maximum(np.linalg.norm(tangent_2, axis=1, keepdims=True), 1e-12)
    if single:
        return tangent_1[0].astype(np.float32), tangent_2[0].astype(np.float32)
    return tangent_1.astype(np.float32), tangent_2.astype(np.float32)


def surface_covariance(
    normals: np.ndarray,
    spacing_h: float,
    tangent_factor: float = 0.75,
    normal_ratio: float = 0.1,
) -> tuple[np.ndarray, np.ndarray]:
    """Rotation frames and per-axis scales for surface Gaussians.

    Tangent sigma = ``tangent_factor * spacing_h`` in both tangent directions
    (isotropic), normal sigma = ``normal_ratio * tangent_sigma``.  These are
    rendering parameters, not accuracy claims.
    """
    if not np.isfinite(spacing_h) or spacing_h <= 0:
        raise MetricError(f"spacing_h must be positive finite, got {spacing_h}")
    if not 0 < normal_ratio <= 1:
        raise MetricError(f"normal_ratio must be in (0,1], got {normal_ratio}")
    normals = np.asarray(normals, dtype=np.float64)
    single = normals.ndim == 1
    if single:
        normals = normals[None, :]
    t1, t2 = tangent_basis(normals.astype(np.float64))
    n = normals.astype(np.float64)
    frames = np.stack([t1, t2, n], axis=2)  # (N, 3, 3), columns are the frame axes
    tangent_sigma = tangent_factor * spacing_h
    normal_sigma = normal_ratio * tangent_sigma
    scales_out = np.zeros((len(normals), 3), dtype=np.float64)
    scales_out[:, 0] = tangent_sigma
    scales_out[:, 1] = tangent_sigma
    scales_out[:, 2] = normal_sigma
    # The tangent axes are isotropic here, so their anisotropy is 1.0 and well
    # inside max_tangent_anisotropy.  That bound governs tangent-vs-tangent only;
    # the normal axis is flattened on purpose and must not trip an all-axis rule.
    if single:
        return frames[0].astype(np.float32), scales_out[0].astype(np.float32)
    return frames.astype(np.float32), scales_out.astype(np.float32)


def quaternion_from_rotation(matrix: np.ndarray) -> np.ndarray:
    """Rotation matrix (3x3) -> unit quaternion (w, x, y, z)."""
    matrix = np.asarray(matrix, dtype=np.float64)
    trace = np.trace(matrix)
    if trace > 0:
        s = np.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (matrix[2, 1] - matrix[1, 2]) / s
        y = (matrix[0, 2] - matrix[2, 0]) / s
        z = (matrix[1, 0] - matrix[0, 1]) / s
    elif matrix[0, 0] > matrix[1, 1] and matrix[0, 0] > matrix[2, 2]:
        s = np.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2]) * 2.0
        w = (matrix[2, 1] - matrix[1, 2]) / s
        x = 0.25 * s
        y = (matrix[0, 1] + matrix[1, 0]) / s
        z = (matrix[0, 2] + matrix[2, 0]) / s
    elif matrix[1, 1] > matrix[2, 2]:
        s = np.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2]) * 2.0
        w = (matrix[0, 2] - matrix[2, 0]) / s
        x = (matrix[0, 1] + matrix[1, 0]) / s
        y = 0.25 * s
        z = (matrix[1, 2] + matrix[2, 1]) / s
    else:
        s = np.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1]) * 2.0
        w = (matrix[1, 0] - matrix[0, 1]) / s
        x = (matrix[0, 2] + matrix[2, 0]) / s
        y = (matrix[1, 2] + matrix[2, 1]) / s
        z = 0.25 * s
    quat = np.array([w, x, y, z])
    return (quat / np.linalg.norm(quat)).astype(np.float32)


@dataclass
class SurfaceGaussians:
    """A deterministic, source-supported Gaussian set ready for PLY export."""

    positions: np.ndarray  # (N,3) room frame, metres
    frames: np.ndarray     # (N,3,3) rotation matrices, columns = frame axes
    scales: np.ndarray     # (N,3) per-axis sigmas, metres
    opacities: np.ndarray  # (N,) in [0,1]
    sh0: np.ndarray        # (N,3) SH degree-0 coefficients
    geometry_only: bool = False
    """True when colour is neutral/invented rather than photo-sampled."""

    def __len__(self) -> int:
        return len(self.positions)

    def quaternions(self) -> np.ndarray:
        return np.stack([quaternion_from_rotation(frame) for frame in self.frames])

    def log_scales(self) -> np.ndarray:
        return np.log(np.maximum(self.scales, 1e-12)).astype(np.float32)

    def opacity_logits(self) -> np.ndarray:
        return inverse_sigmoid(self.opacities)

    def export_ply(self, path: pathlib.Path) -> None:
        count = len(self)
        if count == 0:
            raise MetricError("refusing to export an empty Gaussian set")
        if pathlib.Path(path).exists():
            raise MetricError(f"refusing to overwrite existing export: {path}")
        positions = np.asarray(self.positions, dtype=np.float32)
        scales = np.asarray(self.scales, dtype=np.float32)
        opacities = np.asarray(self.opacities, dtype=np.float32)
        sh0 = np.asarray(self.sh0, dtype=np.float32)
        quats = self.quaternions()
        if not (
            np.isfinite(positions).all()
            and np.isfinite(scales).all()
            and np.isfinite(opacities).all()
            and np.isfinite(sh0).all()
            and np.isfinite(quats).all()
        ):
            raise MetricError("refusing to export non-finite Gaussian attributes")
        header = (
            "ply\nformat binary_little_endian 1.0\n"
            f"element vertex {count}\n"
            "property float x\nproperty float y\nproperty float z\n"
            "property float f_dc_0\nproperty float f_dc_1\nproperty float f_dc_2\n"
            "property float opacity\n"
            "property float scale_0\nproperty float scale_1\nproperty float scale_2\n"
            "property float rot_0\nproperty float rot_1\nproperty float rot_2\nproperty float rot_3\n"
            "end_header\n"
        )
        log_scales = self.log_scales()
        logits = self.opacity_logits()
        data = np.zeros(
            count,
            dtype=[
                ("x", "f4"), ("y", "f4"), ("z", "f4"),
                ("f_dc_0", "f4"), ("f_dc_1", "f4"), ("f_dc_2", "f4"),
                ("opacity", "f4"),
                ("scale_0", "f4"), ("scale_1", "f4"), ("scale_2", "f4"),
                ("rot_0", "f4"), ("rot_1", "f4"), ("rot_2", "f4"), ("rot_3", "f4"),
            ],
        )
        data["x"], data["y"], data["z"] = positions[:, 0], positions[:, 1], positions[:, 2]
        data["f_dc_0"], data["f_dc_1"], data["f_dc_2"] = sh0[:, 0], sh0[:, 1], sh0[:, 2]
        data["opacity"] = logits
        data["scale_0"], data["scale_1"], data["scale_2"] = log_scales[:, 0], log_scales[:, 1], log_scales[:, 2]
        data["rot_0"], data["rot_1"], data["rot_2"], data["rot_3"] = quats[:, 0], quats[:, 1], quats[:, 2], quats[:, 3]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(header.encode("ascii") + data.tobytes())
