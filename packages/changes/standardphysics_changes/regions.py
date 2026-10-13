"""Group changed points into object-sized regions and fit an upright box to each one."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import binary_dilation, label
from scipy.spatial import ConvexHull, QhullError

from .evidence import GONE, KEPT


@dataclass(frozen=True)
class RegionRules:
    voxel_m: float = 0.04
    above_floor_m: float = 0.03
    min_points: int = 150
    min_extent_m: float = 0.12
    min_thickness_m: float = 0.1
    min_height_m: float = 0.06
    grow_steps: int = 6


@dataclass
class Box:
    center: np.ndarray
    size: np.ndarray
    yaw: float
    """Radians about z, the direction of the box's x side."""

    @property
    def volume(self) -> float:
        return float(np.prod(self.size))

    def corners(self) -> np.ndarray:
        c, s = np.cos(self.yaw), np.sin(self.yaw)
        half = self.size / 2
        signs = np.array([[x, y, z] for z in (-1, 1) for y in (-1, 1) for x in (-1, 1)], dtype=np.float64)
        local = signs * half
        rotation = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        return local @ rotation.T + self.center

    def as_dict(self) -> dict:
        return {
            "center": [round(float(v), 3) for v in self.center],
            "size": [round(float(v), 3) for v in self.size],
            "yaw_deg": round(float(np.degrees(self.yaw)), 1),
        }


@dataclass
class Region:
    kind: str
    """"removed" for before-video points that are gone, "added" for after-video points that are new."""
    epoch: int
    point_ids: np.ndarray
    box: Box
    seed_count: int
    names: dict = field(default_factory=dict)
    descriptor: np.ndarray | None = None


def _grid(points: np.ndarray, voxel: float) -> tuple[np.ndarray, np.ndarray, tuple]:
    origin = points.min(axis=0) - voxel
    cells = np.floor((points - origin) / voxel).astype(np.int64)
    shape = tuple(int(n) for n in cells.max(axis=0) + 2)
    return cells, origin, shape


def _occupancy(cells: np.ndarray, shape: tuple, mask: np.ndarray) -> np.ndarray:
    grid = np.zeros(shape, dtype=bool)
    grid[tuple(cells[mask].T)] = True
    return grid


def _grow(seed: np.ndarray, allowed: np.ndarray, steps: int) -> np.ndarray:
    grown = seed.copy()
    structure = np.ones((3, 3, 3), dtype=bool)
    for _ in range(steps):
        wider = binary_dilation(grown, structure) & allowed
        if wider.sum() == grown.sum():
            break
        grown = wider
    return grown | seed


def fit_box(points: np.ndarray) -> Box:
    """The smallest-footprint upright box, standing on the lowest point."""
    low, high = np.percentile(points[:, 2], [1, 99])
    xy = points[:, :2]
    yaw, extent, centre_xy = _min_area_rectangle(xy)
    return Box(np.array([*centre_xy, (low + high) / 2]), np.array([*extent, max(high - low, 0.01)]), yaw)


def _hull_vertices(xy: np.ndarray) -> np.ndarray:
    try:
        return xy[ConvexHull(xy).vertices]
    except (QhullError, ValueError):
        return xy


def _without_stragglers(xy: np.ndarray) -> np.ndarray:
    distance = np.linalg.norm(xy - np.median(xy, axis=0), axis=1)
    trimmed = xy[distance <= np.percentile(distance, 98) + 1e-6]
    return trimmed if len(trimmed) >= 3 else xy


def _min_area_rectangle(xy: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    hull = _hull_vertices(_without_stragglers(xy))
    edges = np.diff(np.vstack([hull, hull[:1]]), axis=0)
    angles = np.unique(np.mod(np.arctan2(edges[:, 1], edges[:, 0]), np.pi / 2)) if len(hull) > 2 else np.array([0.0])
    best = None
    for angle in angles:
        c, s = np.cos(angle), np.sin(angle)
        local = hull @ np.array([[c, -s], [s, c]])
        low, high = local.min(axis=0), local.max(axis=0)
        area = float(np.prod(high - low))
        if best is None or area < best[0]:
            centre = np.array([[c, -s], [s, c]]) @ ((low + high) / 2)
            best = (area, float(angle), high - low, centre)
    return best[1], best[2], best[3]


def _component_ok(points: np.ndarray, rules: RegionRules) -> bool:
    if len(points) < rules.min_points:
        return False
    extent = np.percentile(points, 98, axis=0) - np.percentile(points, 2, axis=0)
    return float(extent.max()) >= rules.min_extent_m and float(np.percentile(points[:, 2], 98)) >= rules.min_height_m


def find_regions(points: np.ndarray, status: np.ndarray, kind: str, epoch: int,
                 rules: RegionRules = RegionRules()) -> list[Region]:
    """Connected clusters of gone points, grown through neighbours the other video never contradicted."""
    raised = points[:, 2] > rules.above_floor_m
    seeds = raised & (status == GONE)
    if seeds.sum() < rules.min_points:
        return []
    cells, _, shape = _grid(points, rules.voxel_m)
    seed_grid = _occupancy(cells, shape, seeds)
    allowed = _occupancy(cells, shape, raised & (status != KEPT))
    labels, count = label(binary_dilation(seed_grid, np.ones((3, 3, 3), dtype=bool)) & allowed)
    regions = []
    for index in range(1, count + 1):
        region = _region_from_label(labels == index, cells, seeds, raised, allowed, kind, epoch, rules)
        if region is not None:
            regions.append(region)
    return regions


def _region_from_label(component, cells, seeds, raised, allowed, kind, epoch, rules) -> Region | None:
    in_component = component[tuple(cells.T)]
    seed_ids = np.flatnonzero(in_component & seeds)
    if len(seed_ids) < rules.min_points:
        return None
    grown = _grow(component, allowed, rules.grow_steps)
    member_ids = np.flatnonzero(grown[tuple(cells.T)] & raised)
    return Region(kind=kind, epoch=epoch, point_ids=member_ids, box=Box(np.zeros(3), np.zeros(3), 0.0),
                  seed_count=len(seed_ids))


def finish_regions(regions: list[Region], points: np.ndarray, rules: RegionRules = RegionRules()) -> list[Region]:
    """Boxes for the regions big enough to be objects.

    A region thinner than `min_thickness_m` across its footprint is nearly always a
    sliver along a silhouette, where the two reconstructions disagree by a pixel or two.
    The cost is that a genuinely thin object, a broom or a frame leaning on a wall, is
    not reported.
    """
    kept = []
    for region in regions:
        members = points[region.point_ids]
        if not _component_ok(members, rules):
            continue
        region.box = fit_box(members)
        if float(region.box.size[:2].min()) >= rules.min_thickness_m:
            kept.append(region)
    return kept
