"""Render-efficiency benchmark: paired-image metrics, scoring, manifest hashing, and surface splats."""

from .builder import BuildResult, build_surface_gaussians, sample_mesh
from .manifest import canonical_hash, sha256_bytes, sha256_file, validate_expected_files, validate_view_list
from .metrics import MetricError, masked_mse, psnr, ssim, uncovered_fraction
from .scoring import (
    GateVerdicts,
    aggregate_score,
    clip,
    hard_gate_verdicts,
    q_critical,
    q_psnr,
    q_ssim,
    quality_score,
    resource_gain,
)
from .surface_splats import (
    SH0_NORMALIZER,
    SurfaceGaussians,
    inverse_sigmoid,
    quaternion_from_rotation,
    rgb_from_sh0,
    sh0_from_rgb,
    surface_covariance,
    tangent_basis,
)

__all__ = [
    "BuildResult",
    "GateVerdicts",
    "MetricError",
    "SH0_NORMALIZER",
    "SurfaceGaussians",
    "aggregate_score",
    "build_surface_gaussians",
    "canonical_hash",
    "clip",
    "hard_gate_verdicts",
    "inverse_sigmoid",
    "masked_mse",
    "psnr",
    "q_critical",
    "q_psnr",
    "q_ssim",
    "quality_score",
    "quaternion_from_rotation",
    "resource_gain",
    "rgb_from_sh0",
    "sample_mesh",
    "sha256_bytes",
    "sha256_file",
    "sh0_from_rgb",
    "ssim",
    "surface_covariance",
    "tangent_basis",
    "uncovered_fraction",
    "validate_expected_files",
    "validate_view_list",
]
