"""Pair a disappearance with an appearance when they are the same object moved."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from .regions import Region


@dataclass(frozen=True)
class MatchRules:
    min_appearance: float = 0.55
    max_size_ratio: float = 2.2
    min_move_m: float = 0.15
    name_bonus: float = 0.15


@dataclass
class Move:
    removed: Region
    added: Region
    distance_m: float
    turn_deg: float | None
    similarity: float


def appearance(a: Region, b: Region) -> float:
    if a.descriptor is None or b.descriptor is None:
        return 0.0
    return float(a.descriptor @ b.descriptor)


def _size_ratio(a: Region, b: Region) -> float:
    big = np.maximum(np.sort(a.box.size), 1e-3)
    small = np.maximum(np.sort(b.box.size), 1e-3)
    return float(np.exp(np.mean(np.abs(np.log(big / small)))))


def _same_name(a: Region, b: Region) -> bool:
    return bool(a.names.get("name")) and a.names.get("name") == b.names.get("name")


def pair_score(a: Region, b: Region, rules: MatchRules) -> float | None:
    """How alike two regions are, or None when they cannot be the same object."""
    score = appearance(a, b) + (rules.name_bonus if _same_name(a, b) else 0.0)
    distance = float(np.linalg.norm(a.box.center[:2] - b.box.center[:2]))
    if score < rules.min_appearance or _size_ratio(a, b) > rules.max_size_ratio or distance < rules.min_move_m:
        return None
    return score


def turn_costs(before: np.ndarray, after: np.ndarray, step_deg: float = 5.0) -> tuple[np.ndarray, np.ndarray]:
    """How badly the old shape, turned by each yaw, overlays the new one."""
    a = _thin(before - np.median(before, axis=0))
    b = _thin(after - np.median(after, axis=0))
    tree = cKDTree(b)
    angles = np.arange(-180 + step_deg, 180 + step_deg / 2, step_deg)
    costs = []
    for angle in np.radians(angles):
        c, s = np.cos(angle), np.sin(angle)
        turned = a @ np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
        costs.append(np.median(tree.query(turned)[0]) + np.median(cKDTree(turned).query(b)[0]))
    return angles, np.array(costs)


def estimate_turn(before: np.ndarray, after: np.ndarray, step_deg: float = 5.0) -> float | None:
    """The yaw in degrees that best lays the old shape onto the new one, or None when the shape can't tell.

    Height stays in the comparison, so a chair's tall back tells its front from its rear
    even when the footprint alone is nearly square. A stool or a box looks the same after
    a quarter or half turn; when a clearly different yaw fits almost as well as the best,
    the turn is unknowable and is not reported.
    """
    angles, costs = turn_costs(before, after, step_deg)
    best = int(np.argmin(costs))
    apart = np.abs((angles - angles[best] + 180) % 360 - 180) >= 45
    if np.any(apart & (costs <= costs[best] * 1.15 + 0.005)):
        return None
    return float(angles[best])


def _thin(points: np.ndarray, cap: int = 1500) -> np.ndarray:
    if len(points) <= cap:
        return points
    return points[np.random.default_rng(0).choice(len(points), cap, replace=False)]


def pair_moves(removed: list[Region], added: list[Region], points: np.ndarray,
               rules: MatchRules = MatchRules()) -> list[Move]:
    if not removed or not added:
        return []
    scores = np.full((len(removed), len(added)), -np.inf)
    for i, a in enumerate(removed):
        for j, b in enumerate(added):
            score = pair_score(a, b, rules)
            if score is not None:
                scores[i, j] = score
    rows, cols = linear_sum_assignment(np.where(np.isfinite(scores), -scores, 1e6))
    moves = []
    for i, j in zip(rows, cols):
        if np.isfinite(scores[i, j]):
            a, b = removed[i], added[j]
            turn = estimate_turn(points[a.point_ids], points[b.point_ids])
            distance = float(np.linalg.norm(b.box.center[:2] - a.box.center[:2]))
            moves.append(Move(a, b, distance, turn, float(scores[i, j])))
    return moves
