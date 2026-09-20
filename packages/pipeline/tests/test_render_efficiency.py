"""Gate 0 fixtures for the render-efficiency evaluator.

These prove the metric and scoring code before any experiment runs: identical
images score exactly 50 against themselves, bad evidence fails loudly, and the
hard gates reject a candidate that is faster but destroys critical detail.
"""

from __future__ import annotations

import numpy as np
import pytest
from standardphysics_pipeline.render_efficiency import (
    MetricError,
    aggregate_score,
    canonical_hash,
    hard_gate_verdicts,
    masked_mse,
    psnr,
    quality_score,
    resource_gain,
    ssim,
    uncovered_fraction,
    validate_expected_files,
    validate_view_list,
)


def _image(height: int = 64, width: int = 96, seed: int = 1729) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.random((height, width, 3))


def _mask(height: int = 64, width: int = 96) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    mask[8:-8, 8:-8] = True
    return mask


def test_identical_image_scores_exactly_fifty():
    image = _image()
    mask = _mask()
    psnr_c = psnr(image, image, mask)
    ssim_c = ssim(image, image, mask)
    quality = quality_score(psnr_c, psnr_c, ssim_c, ssim_c, 0.0)
    score = aggregate_score(quality, 100.0, 100.0, 1e9, 1e9, 1e6, 1e6, 16.0, 16.0)
    assert quality == pytest.approx(50.0)
    assert score == pytest.approx(50.0)


def test_identical_image_psnr_is_capped_at_100():
    image = _image()
    assert psnr(image, image, _mask()) == pytest.approx(100.0)


def test_known_added_error_lowers_metrics():
    image = _image()
    mask = _mask()
    rng = np.random.default_rng(7)
    noisy = np.clip(image + rng.normal(0.0, 0.05, image.shape), 0.0, 1.0)
    assert psnr(noisy, image, mask) < psnr(image, image, mask)
    assert ssim(noisy, image, mask) < ssim(image, image, mask)


def test_masked_mse_channel_averaged():
    reference = np.zeros((8, 8, 3))
    candidate = np.zeros((8, 8, 3))
    candidate[:, :, 0] = 1.0
    assert masked_mse(reference, candidate, np.ones((8, 8), dtype=bool)) == pytest.approx(1.0 / 3.0)


def test_nonfinite_reference_fails():
    image = _image()
    bad = image.copy()
    bad[0, 0, 0] = np.nan
    with pytest.raises(MetricError):
        psnr(bad, image, _mask())


def test_nonfinite_candidate_fails():
    image = _image()
    bad = image.copy()
    bad[1, 1, 1] = np.inf
    with pytest.raises(MetricError):
        ssim(image, bad, _mask())


def test_wrong_resolution_fails():
    with pytest.raises(MetricError):
        psnr(_image(32, 32), _image(64, 96), _mask())


def test_mask_shape_mismatch_fails():
    image = _image()
    with pytest.raises(MetricError):
        psnr(image, image, np.ones((32, 32), dtype=bool))


def test_empty_mask_fails():
    image = _image()
    with pytest.raises(MetricError):
        psnr(image, image, np.zeros((64, 96), dtype=bool))


def test_ssim_rejects_too_thin_mask():
    image = _image()
    thin = np.zeros((64, 96), dtype=bool)
    thin[:, 47:49] = True
    with pytest.raises(MetricError):
        ssim(image, image, thin)


def test_missing_image_fails():
    with pytest.raises(MetricError):
        validate_expected_files(["/nonexistent/path/nope.jpg"])


def test_altered_input_hash_differs():
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})


def test_shortened_view_list_fails():
    with pytest.raises(MetricError):
        validate_view_list([])


def test_duplicate_view_fails():
    with pytest.raises(MetricError):
        validate_view_list(
            [{"file_path": "a.jpg"}, {"file_path": "a.jpg"}, {"file_path": "b.jpg"}]
        )


def test_view_list_accepts_unique():
    validate_view_list([{"file_path": "a.jpg"}, {"file_path": "b.jpg"}])


def test_coverage_threshold():
    alpha = np.array([[0.9, 0.4], [0.8, 0.1]])
    supported = np.array([[True, True], [True, True]])
    assert uncovered_fraction(alpha, supported) == pytest.approx(0.5)


def test_coverage_nonfinite_fails():
    alpha = np.array([[np.nan]])
    supported = np.ones((1, 1), dtype=bool)
    with pytest.raises(MetricError):
        uncovered_fraction(alpha, supported)


def test_resource_gain_requires_positive_finite():
    with pytest.raises(MetricError):
        resource_gain(0.0, 1.0)
    with pytest.raises(MetricError):
        resource_gain(-1.0, 1.0)
    assert resource_gain(2.0, 1.0) == pytest.approx(100.0)


def test_missing_timing_marks_gate_unknown():
    verdicts = hard_gate_verdicts(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None, False, True)
    assert verdicts.frame_p95 is None
    assert not verdicts.all_pass()
    assert verdicts.any_unknown()


def test_faster_candidate_destroying_detail_fails_gate():
    image = _image()
    mask = _mask()
    baseline_psnr = psnr(image, image, mask)
    rng = np.random.default_rng(3)
    destroyed = np.clip(image + rng.normal(0.0, 0.3, image.shape), 0.0, 1.0)
    candidate_psnr = psnr(destroyed, image, mask)
    drop = candidate_psnr - baseline_psnr
    verdicts = hard_gate_verdicts(drop, drop, -1.0, drop, drop, 0.0, 0.5, True, True)
    assert verdicts.critical_roi is False
    assert not verdicts.all_pass()
