"""Where a 3D region shows up in a camera view, and crops of it for people and models."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image
from scipy.ndimage import binary_closing, binary_dilation

from .evidence import DepthLookup, Tolerance, compare
from .geometry import project
from .regions import Box
from .video import DETAIL_SCALE
from .views import View

OUTLINE = (255, 120, 0)


@dataclass
class Sighting:
    view: View
    mask: np.ndarray
    visible: int
    score: float

    def bounds(self, margin: float) -> tuple[int, int, int, int]:
        rows, cols = np.nonzero(self.mask)
        return padded_bounds(cols.min(), rows.min(), cols.max() + 1, rows.max() + 1, self.view.shape, margin)


def _window(centre: float, side: float, limit: int) -> tuple[int, int]:
    start = min(max(centre - side / 2, 0), limit - side)
    return int(round(start)), int(round(start + side))


def padded_bounds(left, top, right, bottom, shape, margin: float) -> tuple[int, int, int, int]:
    """A square around the box with `margin` to spare, slid back inside the frame rather than cut by it."""
    height, width = shape
    side = min(max(right - left, bottom - top, 24) * (1 + margin), height, width)
    x0, x1 = _window((left + right) / 2, side, width)
    y0, y1 = _window((top + bottom) / 2, side, height)
    return x0, y0, x1, y1


def _mask_from(u: np.ndarray, v: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    mask[np.clip(v.astype(int), 0, shape[0] - 1), np.clip(u.astype(int), 0, shape[1] - 1)] = True
    return binary_closing(binary_dilation(mask, iterations=2), iterations=2)


def sightings(points: np.ndarray, views: list[View], tolerance: Tolerance = Tolerance()) -> list[Sighting]:
    """Views where the region's own surface is visible, best first."""
    found = []
    for view in views:
        agree, _, _ = compare(points, DepthLookup.of(view, tolerance), tolerance)
        if agree.sum() < 20:
            continue
        u, v, _ = project(points[agree], view)
        mask = _mask_from(u, v, view.shape)
        found.append(Sighting(view, mask, int(agree.sum()), _framing_score(mask, int(agree.sum()))))
    return sorted(found, key=lambda s: s.score, reverse=True)


def touches_edge(mask: np.ndarray, margin_px: int = 12) -> bool:
    """Whether a region runs into the frame's edge, where the picture may have cut part of it off.

    The margin is wider than the pixels left out of the cloud at the edge, so a region that
    stops there because its points were dropped still counts as touching.
    """
    rows, cols = np.nonzero(mask)
    height, width = mask.shape
    return bool(rows.min() <= margin_px or cols.min() <= margin_px or rows.max() >= height - 1 - margin_px
                or cols.max() >= width - 1 - margin_px)


def _edge_bands(shape: tuple[int, int], margin_px: int) -> list[tuple[np.ndarray, tuple]]:
    """For each side of the frame, the pixels near it and the index of the edge pixel each one lines up with."""
    height, width = shape
    rows, cols = np.mgrid[0:height, 0:width]
    return [
        (cols < margin_px, (rows, np.zeros_like(cols))),
        (cols >= width - margin_px, (rows, np.full_like(cols, width - 1))),
        (rows < margin_px, (np.zeros_like(rows), cols)),
        (rows >= height - margin_px, (np.full_like(rows, height - 1), cols)),
    ]


def runs_off_frame(sighting: Sighting, tolerance: Tolerance = Tolerance(), margin_px: int = 12) -> bool:
    """Whether the region's surface carries on past the frame's edge, rather than stopping just short of it.

    A vase near the top of the frame touches the edge band, but above it the picture shows
    wall at another depth. A crate cut off by the frame shows its own surface right up to
    the last pixel, at the depth it had just inside.
    """
    depth = sighting.view.depth
    continuing = near = 0
    for band, (edge_rows, edge_cols) in _edge_bands(depth.shape, margin_px):
        inside = sighting.mask & band & (depth > 0)
        if not inside.any():
            continue
        own = depth[inside]
        edge = depth[edge_rows[inside], edge_cols[inside]]
        near += int(inside.sum())
        continuing += int(np.sum((edge > 0) & (np.abs(edge - own) < tolerance.at(own))))
    return near > 0 and continuing >= 0.5 * near


def _framing_score(mask: np.ndarray, visible: int) -> float:
    """Many visible points, away from the frame edge, so the object is whole in the picture."""
    rows, cols = np.nonzero(mask)
    height, width = mask.shape
    centre = np.hypot(cols.mean() / width - 0.5, rows.mean() / height - 0.5)
    return visible * (0.5 if touches_edge(mask) else 1.0) * (1.0 - centre)


def empty_spot_view(points: np.ndarray, views: list[View], tolerance: Tolerance = Tolerance()) -> View | None:
    """The other recording's view that saw most clearly through where the region is."""
    best, best_count = None, 0
    for view in views:
        _, through, _ = compare(points, DepthLookup.of(view, tolerance), tolerance)
        if through.sum() > best_count:
            best, best_count = view, int(through.sum())
    return best


def box_pixels(box: Box, view: View) -> np.ndarray | None:
    u, v, z = project(box.corners(), view)
    if np.any(z <= 0.05):
        return None
    return np.stack([u, v], axis=1)


def detail_crop(view: View, bounds: tuple[int, int, int, int]) -> Image.Image:
    left, top, right, bottom = (int(b * DETAIL_SCALE) for b in bounds)
    return Image.fromarray(view.detail[top:bottom, left:right])


def outlined(sighting: Sighting, margin: float) -> Image.Image:
    """A crop with the region traced, so a model knows which object is meant."""
    bounds = sighting.bounds(margin)
    left, top, right, bottom = bounds
    edge = (binary_dilation(sighting.mask, iterations=2) & ~sighting.mask)[top:bottom, left:right]
    crop = np.asarray(detail_crop(sighting.view, bounds)).copy()
    big = _upscale(edge, crop.shape)
    crop[big] = OUTLINE
    return Image.fromarray(crop)


def _upscale(mask: np.ndarray, shape: tuple) -> np.ndarray:
    return np.kron(mask, np.ones((DETAIL_SCALE, DETAIL_SCALE), dtype=bool))[:shape[0], :shape[1]]


def isolated(sighting: Sighting, margin: float = 0.15) -> Image.Image:
    """The region alone on grey, for an appearance descriptor that ignores the surroundings."""
    bounds = sighting.bounds(margin)
    left, top, right, bottom = bounds
    mask = binary_dilation(sighting.mask, iterations=3)[top:bottom, left:right]
    crop = np.asarray(detail_crop(sighting.view, bounds)).copy()
    crop[~_upscale(mask, crop.shape)] = 128
    return Image.fromarray(crop)
