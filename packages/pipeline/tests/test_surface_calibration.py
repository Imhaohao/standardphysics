"""Synthetic calibration tests: transmittance compositing (A01) and the capped production sampler (A02)."""

from __future__ import annotations

import numpy as np
import pytest
from standardphysics_pipeline.render_efficiency import MetricError
from standardphysics_pipeline.render_efficiency.builder import sample_mesh
from standardphysics_pipeline.render_efficiency.calibration import (
    DEFAULT_RINGS,
    HOLE_ALPHA_THRESHOLD,
    OPACITY_OPTIONS,
    TANGENT_FACTORS,
    TRUNCATION_TOLERANCE,
    calibrate_capped_sampler,
    evaluate_pair,
    fill_status,
    lattice_offsets,
    pick_parameters,
    plane_alpha_composited,
    plane_alpha_field,
    plane_alpha_sum,
    synthetic_calibration_mesh,
    transmittance_alpha,
    truncation_error_bound,
)
from standardphysics_pipeline.render_efficiency.surface_splats import surface_covariance


def _lattice_composited(h: float, c: float, o: float, rings: int) -> np.ndarray:
    offsets = lattice_offsets(h, rings)
    probes = np.array([[0.0, 0.0], [h / 4, h / 4], [h / 2, h / 2]])
    delta = probes[:, None, :] - offsets[None, :, :]
    return plane_alpha_composited((delta * delta).sum(axis=2), c * h, o)


def test_a01_two_half_alpha_layers_composite_to_075():
    accumulated = transmittance_alpha(np.array([0.5, 0.5]))
    assert accumulated[0] == pytest.approx(0.5)
    assert accumulated[-1] == pytest.approx(0.75)


def test_a01_zero_opacity_is_zero_and_never_exceeds_one():
    assert transmittance_alpha(np.array([0.0, 0.0, 0.0])) == pytest.approx(0.0)
    rng = np.random.default_rng(7)
    stacked = rng.random((100, 40))
    composed = transmittance_alpha(stacked)
    assert (composed >= 0.0).all() and (composed <= 1.0).all()


def test_a01_brightness_is_not_alpha_sum():
    distances_sq = np.zeros((1, 2))
    summed = plane_alpha_sum(distances_sq, 0.5, 0.5)
    composited = plane_alpha_composited(distances_sq, 0.5, 0.5)
    assert summed[0] == pytest.approx(1.0)
    assert composited[0] == pytest.approx(0.75)


def test_a01_composited_monotone_and_ordered():
    rng = np.random.default_rng(11)
    base = rng.random(20) * 0.9
    extra = np.concatenate([base, np.array([0.5])])
    assert transmittance_alpha(extra)[-1] > transmittance_alpha(base)[-1]


def test_a01_composited_rejects_out_of_range():
    with pytest.raises(MetricError):
        transmittance_alpha(np.array([1.2]))
    with pytest.raises(MetricError):
        transmittance_alpha(np.array([np.nan]))
    with pytest.raises(MetricError):
        transmittance_alpha(np.array([]))


def test_a01_identical_parameters_consistent():
    first = plane_alpha_field(0.05, 0.75, 0.5)
    second = plane_alpha_field(0.05, 0.75, 0.5)
    assert np.array_equal(first, second)
    assert evaluate_pair(0.05, 0.75, 0.5)["min_composited_alpha"] == pytest.approx(float(first.min()))


def test_a01_composited_field_is_bounded_below_summed_field():
    offsets = lattice_offsets(0.05, DEFAULT_RINGS)
    probes = np.array([[0.0, 0.0]])
    delta = probes[:, None, :] - offsets[None, :, :]
    dist_sq = (delta * delta).sum(axis=2)
    summed = plane_alpha_sum(dist_sq, 0.05 * 0.75, 0.5)
    composited = plane_alpha_composited(dist_sq, 0.05 * 0.75, 0.5)
    assert composited[0] < summed[0]
    assert composited[0] <= 1.0


def test_a01_hole_status_uses_composited_field():
    tiny = plane_alpha_field(0.05, 0.25, 0.3)
    tiny_holes = float((tiny < HOLE_ALPHA_THRESHOLD).mean())
    assert fill_status(float(tiny.min()), tiny_holes) == "holes"
    filled = plane_alpha_field(0.05, 1.0, 0.5)
    assert fill_status(float(filled.min()), float((filled < HOLE_ALPHA_THRESHOLD).mean())) == "no_holes"


def test_a01_truncation_bound_below_tolerance():
    for factor in TANGENT_FACTORS:
        for opacity in OPACITY_OPTIONS:
            assert truncation_error_bound(factor, opacity, rings=DEFAULT_RINGS) < TRUNCATION_TOLERANCE


def test_a01_pick_parameters_is_policy_option_and_hole_free():
    result = pick_parameters()
    assert result["tangent_factor"] in TANGENT_FACTORS
    assert result["opacity"] in OPACITY_OPTIONS
    assert result["min_composited_alpha_h002"] >= HOLE_ALPHA_THRESHOLD
    assert result["min_composited_alpha_h005"] >= HOLE_ALPHA_THRESHOLD


def test_a02_calibration_mesh_has_varied_orientation_and_scale():
    vertices, triangles = synthetic_calibration_mesh()
    corners = vertices[triangles]
    normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    pairwise = np.abs(normals @ normals.T)
    not_aligned = pairwise[np.triu_indices_from(pairwise, k=1)] < 0.999
    assert not_aligned.sum() > 0, "synthetic mesh must contain non-parallel planes"
    areas = np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1) / 2
    assert areas.max() / areas.min() > 10, "areas must span orders of magnitude"


def test_a02_capped_sampler_area_proportional_and_bounded():
    vertices, triangles = synthetic_calibration_mesh()
    corners = vertices[triangles]
    areas = np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1) / 2
    points, _, owners, _, _ = sample_mesh(vertices, triangles, spacing=0.02, seed=1729, max_samples=150000)
    assert len(points) <= 150000
    for triangle in range(len(triangles)):
        if areas[triangle] > 1e-10 and areas[triangle] / areas.sum() > 1e-3:
            observed = float((owners == triangle).mean())
            expected = float(areas[triangle] / areas.sum())
            assert observed == pytest.approx(expected, rel=0.03)


def test_a02_calibration_sweep_yields_hole_free_option():
    report = calibrate_capped_sampler(spacing=0.02, probe_count=600)
    assert report["sample_count"] <= 150000
    chosen = report["chosen"]
    assert chosen["tangent_factor"] in TANGENT_FACTORS
    assert chosen["opacity"] in OPACITY_OPTIONS
    assert report["density_area_agreement"] > 0.99


def test_calibration_sigma_matches_frozen_covariance_scale():
    h, factor = 0.05, 0.75
    _, scales = surface_covariance(np.array([0.0, 0.0, 1.0]), spacing_h=h, tangent_factor=factor)
    assert float(scales[0]) == pytest.approx(factor * h)
