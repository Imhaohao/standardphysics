"""What the other recording saw at each surface point: the same surface, empty space, or nothing useful.

A point from the before video is tested against every after camera. If an after
camera's depth at that pixel lands on the point, the surface is still there. If the
camera saw farther than the point, its line of sight passed through where the point
was, so the space is now empty. If something nearer blocked the view, or no camera
looked that way, the after video says nothing about the point at all. Keeping that
third answer separate is what stops occlusion and gaps in coverage from being
reported as changes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import maximum_filter, minimum_filter

from .geometry import project
from .views import View

KEPT, GONE, UNSEEN = 0, 1, 2
STATUS_NAMES = ("kept", "gone", "unseen")


@dataclass(frozen=True)
class Tolerance:
    absolute_m: float = 0.05
    relative: float = 0.04
    window_px: int = 9
    edge_margin_px: int = 3

    def at(self, depth: np.ndarray) -> np.ndarray:
        return self.absolute_m + self.relative * depth


@dataclass
class DepthLookup:
    """A view's depth with its local minimum and maximum, so small pose errors are forgiven."""

    view: View
    nearest: np.ndarray
    farthest: np.ndarray

    @classmethod
    def of(cls, view: View, tolerance: Tolerance) -> DepthLookup:
        valid = view.depth > 0
        nearest = minimum_filter(np.where(valid, view.depth, np.inf), size=tolerance.window_px)
        farthest = maximum_filter(np.where(valid, view.depth, 0.0), size=tolerance.window_px)
        return cls(view, nearest, farthest)


@dataclass
class Evidence:
    agree: np.ndarray
    through: np.ndarray
    blocked: np.ndarray

    @classmethod
    def empty(cls, count: int) -> Evidence:
        return cls(*(np.zeros(count, dtype=np.int32) for _ in range(3)))


def _sample(lookup: DepthLookup, points: np.ndarray, tolerance: Tolerance):
    height, width = lookup.view.shape
    u, v, z = project(points, lookup.view)
    margin = tolerance.edge_margin_px
    inside = (z > 0.1) & (u >= margin) & (u < width - margin) & (v >= margin) & (v < height - margin)
    cols = np.clip(u.astype(np.int64), 0, width - 1)
    rows = np.clip(v.astype(np.int64), 0, height - 1)
    centre_valid = lookup.view.depth[rows, cols] > 0
    return inside & centre_valid, z, lookup.nearest[rows, cols], lookup.farthest[rows, cols]


def compare(points: np.ndarray, lookup: DepthLookup, tolerance: Tolerance) -> tuple[np.ndarray, ...]:
    """Three masks over `points`: the view saw the surface, saw past it, or saw something in front."""
    seen, z, nearest, farthest = _sample(lookup, points, tolerance)
    slack = tolerance.at(z)
    through = seen & (nearest > z + slack)
    blocked = seen & (farthest < z - slack)
    agree = seen & ~through & ~blocked
    return agree, through, blocked


def gather(points: np.ndarray, lookups: list[DepthLookup], tolerance: Tolerance) -> Evidence:
    evidence = Evidence.empty(len(points))
    for lookup in lookups:
        agree, through, blocked = compare(points, lookup, tolerance)
        evidence.agree += agree
        evidence.through += through
        evidence.blocked += blocked
    return evidence


def classify(evidence: Evidence, support: np.ndarray | None = None, min_through: int = 2, gone_share: float = 0.7,
             min_support: int = 3) -> np.ndarray:
    """Gone needs repeated sight through the point and little sight of it; no sight either way is unseen.

    `support` counts the frames of the point's own video that agree with it. A surface
    only one or two of its own frames back up is often a depth ghost at a silhouette or
    the frame edge, so it may stay or go unseen but never counts as gone.
    """
    looked = evidence.agree + evidence.through
    share = np.divide(evidence.through, looked, out=np.zeros(len(looked)), where=looked > 0)
    status = np.full(len(looked), UNSEEN, dtype=np.uint8)
    status[evidence.agree > 0] = KEPT
    gone = (evidence.through >= min_through) & (share >= gone_share)
    if support is not None:
        gone &= support >= min_support
    status[gone] = GONE
    return status
