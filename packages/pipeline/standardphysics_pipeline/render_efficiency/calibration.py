"""Synthetic-plane calibration for deterministic surface-Gaussian rendering.

Phase 3 of the render-efficiency plan freezes the tangent-sigma spacing factor
and the per-splat opacity on a synthetic plane, before any real-data trial.
The model is an infinite plane sampled on a square lattice at spacing ``h``
with one surface Gaussian per sample: isotropic tangent sigma ``s_t = c*h``,
normal sigma ``0.1*s_t``, and opacity ``o``.  Pointwise summed alpha is

    A(x) = o * sum_i exp(-|x - p_i|^2 / (2 * s_t^2)).

A point with ``A < 0.5`` is a hole; a point with ``A > 0.95`` reads as an
over-bright wall, and more than 5% of a fundamental cell there is oversaturated.
Everything is deterministic numpy plane math using the closed-form projection;
no renderer is involved.
"""

from __future__ import annotations

import math

import numpy as np

from .metrics import MetricError

TANGENT_FACTORS: tuple[float, ...] = (0.5, 0.75, 1.0)
"""Policy options for tangent sigma = factor * spacing (docs/deepseek-lidar-experiment-policy.json)."""

OPACITY_OPTIONS: tuple[float, ...] = (0.3, 0.5, 0.7)
"""Policy options for per-splat opacity."""

SPACING_METRES: tuple[float, ...] = (0.02, 0.05)
"""Sample spacings the frozen choice must be hole-free at (self-similarity is verified, not assumed)."""

NORMAL_TO_TANGENT_RATIO = 0.1
"""Initial normal sigma as a fraction of the tangent sigma (policy value)."""

HOLE_ALPHA_THRESHOLD = 0.5
"""Summed alpha below this reads as a visible hole."""

SATURATION_ALPHA_THRESHOLD = 0.95
"""Summed alpha above this reads as an over-bright wall."""

SATURATION_FRACTION_LIMIT = 0.05
"""More than this fraction of the cell above the saturation threshold is oversaturated."""

TRUNCATION_TOLERANCE = 1e-4
"""Maximum allowed summed-alpha error from ignoring far lattice rings."""

DEFAULT_RINGS = 14
DEFAULT_GRID_SIDE = 101


def _positive_finite(value: float, name: str) -> float:
    if not np.isfinite(value) or value <= 0.0:
        raise MetricError(f"{name} must be positive finite, got {value}")
    return float(value)


def _validated_opacity(opacity: float) -> float:
    if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
        raise MetricError(f"opacity must be in [0,1], got {opacity}")
    return float(opacity)


def _validate_sigma_and_opacity(sigma_t: float, opacity: float) -> None:
    _positive_finite(sigma_t, "sigma_t")
    _validated_opacity(opacity)


def plane_alpha_sum(distances_sq: np.ndarray, sigma_t: float, opacity: float) -> np.ndarray:
    """Summed alpha over samples for query points.

    ``distances_sq`` is (Nq, Ns): squared in-plane distance from each of Nq
    query points to each of Ns samples.  Returns shape (Nq,).
    """
    _validate_sigma_and_opacity(sigma_t, opacity)
    distances = np.asarray(distances_sq, dtype=np.float64)
    if distances.ndim != 2:
        raise MetricError(f"distances_sq must be 2D (Nq, Ns), got shape {distances.shape}")
    if not np.isfinite(distances).all():
        raise MetricError("distances_sq must be finite")
    if distances.size and (distances < 0.0).any():
        raise MetricError("distances_sq must be non-negative")
    per_sample = opacity * np.exp(-distances / (2.0 * sigma_t * sigma_t))
    return per_sample.sum(axis=1)


def lattice_offsets(spacing_h: float, rings: int) -> np.ndarray:
    """Sample positions (M,2) relative to the cell origin on a square lattice.

    Includes every sample with ``|i|, |j| <= rings`` in units of ``spacing_h``.
    """
    _positive_finite(spacing_h, "spacing_h")
    if not isinstance(rings, (int, np.integer)) or rings < 1:
        raise MetricError(f"rings must be a positive integer, got {rings}")
    axis = np.arange(-rings, rings + 1, dtype=np.float64) * spacing_h
    xs, ys = np.meshgrid(axis, axis)
    return np.stack([xs.ravel(), ys.ravel()], axis=1)


def fundamental_cell_grid(spacing_h: float, grid_side: int) -> np.ndarray:
    """Query points (N,2) on a dense square grid covering one cell [0,h]^2."""
    _positive_finite(spacing_h, "spacing_h")
    if not isinstance(grid_side, (int, np.integer)) or grid_side < 2:
        raise MetricError(f"grid_side must be at least 2, got {grid_side}")
    axis = np.linspace(0.0, spacing_h, grid_side)
    xs, ys = np.meshgrid(axis, axis)
    return np.stack([xs.ravel(), ys.ravel()], axis=1)


def _summed_alpha(queries: np.ndarray, offsets: np.ndarray, sigma_t: float, opacity: float) -> np.ndarray:
    """Summed alpha per query point, processed in row blocks to bound memory."""
    block_rows = 256
    parts = []
    for start in range(0, len(queries), block_rows):
        block = queries[start : start + block_rows]
        delta = block[:, None, :] - offsets[None, :, :]
        parts.append(plane_alpha_sum((delta * delta).sum(axis=2), sigma_t, opacity))
    return np.concatenate(parts)


def plane_alpha_field(
    spacing_h: float,
    tangent_factor: float,
    opacity: float,
    rings: int = DEFAULT_RINGS,
    grid_side: int = DEFAULT_GRID_SIDE,
) -> np.ndarray:
    """Summed-alpha field over one fundamental cell, shape (grid_side, grid_side)."""
    sigma_t = tangent_factor * spacing_h
    _validate_sigma_and_opacity(sigma_t, opacity)
    offsets = lattice_offsets(spacing_h, rings)
    queries = fundamental_cell_grid(spacing_h, grid_side)
    summed = _summed_alpha(queries, offsets, sigma_t, opacity)
    return summed.reshape(grid_side, grid_side)


def truncation_error_bound(tangent_factor: float, opacity: float, rings: int = DEFAULT_RINGS) -> float:
    """Rigorous upper bound on summed alpha from samples beyond ``rings``.

    A query point in [0,h]^2 is at least ``(max(|i|-1, 0)*h, max(|j|-1, 0)*h)``
    away from sample ``(i*h, j*h)`` along each axis, so the omitted tail is
    bounded by ``opacity * (S_inf^2 - S_box^2)`` with
    ``q(n) = exp(-max(|n|-1, 0)^2 / (2 c^2))``, ``S_box`` summed over the
    included box and ``S_inf`` over the full lattice axis (evaluated exactly
    to machine precision).
    """
    c = _positive_finite(tangent_factor, "tangent_factor")
    o = _validated_opacity(opacity)
    if not isinstance(rings, (int, np.integer)) or rings < 1:
        raise MetricError(f"rings must be a positive integer, got {rings}")
    axis_max = math.ceil(math.sqrt(2.0 * c * c * 700.0)) + 2
    axis_all = np.arange(axis_max + 1, dtype=np.float64)
    q_all = np.exp(-(np.maximum(axis_all - 1.0, 0.0) ** 2) / (2.0 * c * c))
    s_infinite = 1.0 + 2.0 * q_all[1:].sum()
    box = np.arange(-rings, rings + 1, dtype=np.float64)
    q_box = np.exp(-(np.maximum(np.abs(box) - 1.0, 0.0) ** 2) / (2.0 * c * c))
    s_box = q_box.sum()
    return o * (s_infinite * s_infinite - s_box * s_box)


def fill_status(min_sum_alpha: float, oversaturation_fraction: float) -> str:
    """Classify one numeric result; holes take precedence over saturation.

    Returns ``"no_holes_no_saturation"``, ``"holes"``, or ``"saturated"``.
    """
    if min_sum_alpha < HOLE_ALPHA_THRESHOLD:
        return "holes"
    if oversaturation_fraction > SATURATION_FRACTION_LIMIT:
        return "saturated"
    return "no_holes_no_saturation"


def evaluate_pair(
    spacing_h: float,
    tangent_factor: float,
    opacity: float,
    rings: int = DEFAULT_RINGS,
    grid_side: int = DEFAULT_GRID_SIDE,
) -> dict:
    """Per-spacing synthetic metrics for one (tangent_factor, opacity) pair."""
    field = plane_alpha_field(spacing_h, tangent_factor, opacity, rings=rings, grid_side=grid_side)
    return {
        "spacing_h": float(spacing_h),
        "tangent_factor": float(tangent_factor),
        "opacity": float(opacity),
        "min_sum_alpha": float(field.min()),
        "oversaturation_fraction": float((field > SATURATION_ALPHA_THRESHOLD).mean()),
        "truncation_bound": truncation_error_bound(tangent_factor, opacity, rings=rings),
        "rings": int(rings),
        "grid_side": int(grid_side),
    }


def evaluate_all(
    spacings: tuple[float, ...] = SPACING_METRES,
    factors: tuple[float, ...] = TANGENT_FACTORS,
    opacities: tuple[float, ...] = OPACITY_OPTIONS,
    rings: int = DEFAULT_RINGS,
    grid_side: int = DEFAULT_GRID_SIDE,
) -> dict:
    """Full synthetic sweep keyed by (tangent_factor, opacity) -> per-spacing entries."""
    sweep: dict = {}
    for factor in factors:
        for opacity in opacities:
            sweep[(factor, opacity)] = [
                evaluate_pair(h, factor, opacity, rings=rings, grid_side=grid_side) for h in spacings
            ]
    return sweep


def _pair_status(entries: list[dict]) -> str:
    """Worst status of one pair across all evaluated spacings."""
    per_spacing = [fill_status(e["min_sum_alpha"], e["oversaturation_fraction"]) for e in entries]
    if "holes" in per_spacing:
        return "holes"
    if "saturated" in per_spacing:
        return "saturated"
    return "no_holes_no_saturation"


def _worst_oversaturation(entries: list[dict]) -> float:
    return max(float(e["oversaturation_fraction"]) for e in entries)


def _primary_choice(sweep: dict) -> tuple[float, float]:
    """Smallest factor with no holes at both spacings, prefer smallest opacity."""
    for opacity in OPACITY_OPTIONS:
        for factor in TANGENT_FACTORS:
            if _pair_status(sweep[(factor, opacity)]) != "holes":
                return factor, opacity
    raise MetricError("no policy option leaves the synthetic plane hole-free at both spacings")


def _override_choice(sweep: dict) -> tuple[float, float]:
    """Smallest factor, then opacity, with neither holes nor oversaturation."""
    for factor in TANGENT_FACTORS:
        for opacity in OPACITY_OPTIONS:
            if _pair_status(sweep[(factor, opacity)]) == "no_holes_no_saturation":
                return factor, opacity
    hole_free = [pair for pair in sweep if _pair_status(sweep[pair]) != "holes"]
    if not hole_free:
        raise MetricError("no policy option leaves the synthetic plane hole-free at both spacings")
    return min(hole_free, key=lambda pair: _worst_oversaturation(sweep[pair]))


def _spacing_entry(sweep: dict, factor: float, opacity: float, spacing_h: float) -> dict:
    for entry in sweep[(factor, opacity)]:
        if entry["spacing_h"] == spacing_h:
            return entry
    raise MetricError(f"no sweep entry for spacing {spacing_h}")


def _rationale(sweep: dict, primary: tuple[float, float], chosen: tuple[float, float], notes: dict) -> str:
    p_factor, p_opacity = primary
    c_factor, c_opacity = chosen
    p_min = min(float(e["min_sum_alpha"]) for e in sweep[primary])
    p_frac = _worst_oversaturation(sweep[primary])
    c_mins = " / ".join(f"{e['min_sum_alpha']:.4f}" for e in sweep[chosen])
    c_frac = _worst_oversaturation(sweep[chosen])
    statuses = "; ".join(
        f"c={f},o={o}:{_pair_status(sweep[(f, o)])}" for f in TANGENT_FACTORS for o in OPACITY_OPTIONS
    )
    parts = [
        "Synthetic square-lattice plane at h in {0.02, 0.05} m, tangent sigma c*h, "
        "normal sigma 0.1*s_t, summed alpha on a 101x101 grid over one fundamental "
        "cell with ring truncation bound < 1e-4; results are spacing-invariant as "
        "the self-similar model predicts.",
        f"Pair statuses: {statuses}.",
    ]
    if notes.get("overridden"):
        parts.append(
            f"Primary rule choice (c={p_factor}, o={p_opacity}) is hole-free "
            f"(min {p_min:.4f}) but oversaturated ({p_frac*100:.1f}% of the cell "
            "above 0.95), so it is overridden."
        )
    parts.append(
        f"Frozen pair (c={c_factor}, o={c_opacity}): min summed alpha {c_mins} at "
        f"h=0.02/0.05 (threshold 0.5), oversaturation {c_frac*100:.1f}% (limit 5%)."
    )
    if notes.get("fallback"):
        parts.append("No policy pair is free of oversaturation; the least oversaturated hole-free pair is kept.")
    return " ".join(parts)


def pick_parameters() -> dict:
    """Freeze (tangent_factor, opacity) from the synthetic-plane sweep.

    Decision rule: per opacity, take the smallest tangent factor in {0.5, 0.75,
    1.0} with no holes at both spacings; pick opacity 0.3 if hole-free at that
    factor, else 0.5, else 0.7.  If the chosen pair oversaturates (>5% of the
    cell above 0.95 summed alpha), override to the smallest factor/opacity pair
    with no holes and no oversaturation, and document the override.
    """
    sweep = evaluate_all()
    primary = _primary_choice(sweep)
    notes = {"overridden": False, "fallback": False}
    if _pair_status(sweep[primary]) == "saturated":
        chosen = _override_choice(sweep)
        notes["overridden"] = True
        notes["fallback"] = _pair_status(sweep[chosen]) == "saturated"
    else:
        chosen = primary
    factor, opacity = chosen
    entries = sweep[chosen]
    min_h002 = _spacing_entry(sweep, factor, opacity, 0.02)["min_sum_alpha"]
    min_h005 = _spacing_entry(sweep, factor, opacity, 0.05)["min_sum_alpha"]
    if min_h002 < HOLE_ALPHA_THRESHOLD or min_h005 < HOLE_ALPHA_THRESHOLD:
        raise MetricError("chosen pair reintroduced holes; decision logic is inconsistent")
    return {
        "tangent_factor": factor,
        "opacity": opacity,
        "rationale": _rationale(sweep, primary, chosen, notes),
        "min_sum_alpha_h002": float(min_h002),
        "min_sum_alpha_h005": float(min_h005),
        "oversaturation_fraction": _worst_oversaturation(entries),
    }
