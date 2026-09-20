"""Synthetic-plane calibration tests for deterministic surface-Gaussian rendering."""

from __future__ import annotations

import numpy as np
import pytest
from standardphysics_pipeline.render_efficiency.calibration import (
    DEFAULT_GRID_SIDE,
    DEFAULT_RINGS,
    HOLE_ALPHA_THRESHOLD,
    OPACITY_OPTIONS,
    SATURATION_ALPHA_THRESHOLD,
    SATURATION_FRACTION_LIMIT,
    TANGENT_FACTORS,
    TRUNCATION_TOLERANCE,
    evaluate_pair,
    fill_status,
    lattice_offsets,
    pick_parameters,
    plane_alpha_field,
    plane_alpha_sum,
    truncation_error_bound,
)
from standardphysics_pipeline.render_efficiency.surface_splats import surface_covariance


def _lattice_summed_alpha(h: float, c: float, o: float, rings: int) -> np.ndarray:
    offsets = lattice_offsets(h, rings)
    probes = np.array([[0.0, 0.0], [h / 4, h / 4], [h / 2, h / 2]])  # corners, edge probe, cell centre
    delta = probes[:, None, :] - offsets[None, :, :]
    return plane_alpha_sum((delta * delta).sum(axis=2), c * h, o)


def test_identical_parameters_return_consistent_min_alpha():
    first = plane_alpha_field(0.05, 0.75, 0.5)
    second = plane_alpha_field(0.05, 0.75, 0.5)
    assert first.shape == (DEFAULT_GRID_SIDE, DEFAULT_GRID_SIDE)
    assert np.array_equal(first, second)
    assert float(first.min()) == pytest.approx(1.76703940, abs=1e-6)
    assert evaluate_pair(0.05, 0.75, 0.5)["min_sum_alpha"] == pytest.approx(first.min())


def test_alpha_sum_matches_closed_form():
    distances_sq = np.array([[0.0, 1.0], [2.0, 0.5]])
    sigma_t, opacity = 0.5, 0.4
    expected = opacity * np.exp(-distances_sq / (2.0 * sigma_t * sigma_t)).sum(axis=1)
    assert np.allclose(plane_alpha_sum(distances_sq, sigma_t, opacity), expected)


def test_alpha_sum_monotone_in_opacity():
    distances_sq = np.array([[0.0, 0.02, 0.08]])
    low = plane_alpha_sum(distances_sq, 0.05, 0.3)
    high = plane_alpha_sum(distances_sq, 0.05, 0.7)
    assert (high > low).all()
    field_low = plane_alpha_field(0.05, 0.75, 0.3)
    field_high = plane_alpha_field(0.05, 0.75, 0.7)
    assert (field_high > field_low).all()


def test_hole_status_flips_from_tiny_to_large_sigma():
    tiny = plane_alpha_field(0.05, 0.25, 0.3)  # far below policy minimum: sparse splats
    large = plane_alpha_field(0.05, 1.0, 0.3)  # dense overlapping splats
    assert fill_status(float(tiny.min()), float((tiny > SATURATION_ALPHA_THRESHOLD).mean())) == "holes"
    assert fill_status(float(large.min()), float((large > SATURATION_ALPHA_THRESHOLD).mean())) == "saturated"
    assert fill_status(0.7629667, 0.0) == "no_holes_no_saturation"
    assert fill_status(0.3, 1.0) == "holes"  # holes win over saturation


def test_default_truncation_bound_is_below_tolerance():
    for factor in TANGENT_FACTORS:
        for opacity in OPACITY_OPTIONS:
            bound = truncation_error_bound(factor, opacity, rings=DEFAULT_RINGS)
            assert bound < TRUNCATION_TOLERANCE


def test_ring_sum_agrees_with_huge_window():
    h = 0.05
    for factor, opacity in ((0.5, 0.3), (1.0, 0.7)):
        ring_sum = _lattice_summed_alpha(h, factor, opacity, rings=DEFAULT_RINGS)
        window_sum = _lattice_summed_alpha(h, factor, opacity, rings=80)
        assert np.abs(ring_sum - window_sum).max() < TRUNCATION_TOLERANCE


def test_pick_parameters_returns_policy_values_without_holes():
    result = pick_parameters()
    assert set(result) == {
        "tangent_factor",
        "opacity",
        "rationale",
        "min_sum_alpha_h002",
        "min_sum_alpha_h005",
        "oversaturation_fraction",
    }
    assert result["tangent_factor"] in TANGENT_FACTORS
    assert result["opacity"] in OPACITY_OPTIONS
    assert result["min_sum_alpha_h002"] >= HOLE_ALPHA_THRESHOLD
    assert result["min_sum_alpha_h005"] >= HOLE_ALPHA_THRESHOLD
    assert result["oversaturation_fraction"] <= SATURATION_FRACTION_LIMIT
    assert result["tangent_factor"] == 0.5
    assert result["opacity"] == 0.5


def test_calibration_sigma_matches_frozen_covariance_scale():
    h, factor = 0.05, 0.75
    _, scales = surface_covariance(np.array([0.0, 0.0, 1.0]), spacing_h=h, tangent_factor=factor)
    assert float(scales[0]) == pytest.approx(factor * h)
