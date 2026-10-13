"""Pair a disappearance with an appearance when they are the same object moved."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from .landmarks import footprint_gap, inside_box
from .regions import Box, Region, fit_box


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


def appearance(a: Region, b: Region) -> float | None:
    """How alike the two look, or None when either has no appearance fingerprint."""
    if a.descriptor is None or b.descriptor is None:
        return None
    return float(a.descriptor @ b.descriptor)


def _size_ratio(a: Region, b: Region) -> float:
    big = np.maximum(np.sort(a.box.size), 1e-3)
    small = np.maximum(np.sort(b.box.size), 1e-3)
    return float(np.exp(np.mean(np.abs(np.log(big / small)))))


PLAIN_NOUNS = frozenset({"object", "small object", "large object"})
ON_TOP_M = 0.05


def _same_name(a: Region, b: Region) -> bool:
    name = a.names.get("name", "")
    return bool(name) and name not in PLAIN_NOUNS and name == b.names.get("name")


def pair_score(a: Region, b: Region, rules: MatchRules) -> float | None:
    """How alike two regions are, or None when they cannot be the same object.

    Without a fingerprint on both, the same specific name has to stand in for looks, and
    such a pair ranks at the bar, below any pair whose fingerprints agree.
    """
    similarity, named = appearance(a, b), _same_name(a, b)
    if similarity is None:
        score = rules.min_appearance if named else -1.0
    else:
        score = similarity + (rules.name_bonus if named else 0.0)
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


def long_axis_deg(box: Box, min_aspect: float = 1.25) -> float | None:
    """Which way a box's long side points, in degrees modulo 180, or None for a nearly square footprint."""
    long_side, short_side = float(box.size[:2].max()), float(box.size[:2].min())
    if long_side < min_aspect * short_side:
        return None
    along_x = box.size[0] >= box.size[1]
    return float(np.degrees(box.yaw) + (0 if along_x else 90)) % 180


def consistent_turn(turn: float | None, before: Box, after: Box, tolerance_deg: float = 20.0) -> float | None:
    """The shape's turn, kept only if it agrees with how an elongated footprint's long side turned.

    An ottoman seen from different sides can overlay best at a wrong angle; its footprint's
    long side still says which way it lies, up to a half turn. When the two disagree the
    turn is unknowable from these views and is left out.
    """
    first, second = long_axis_deg(before), long_axis_deg(after)
    if turn is None or first is None or second is None:
        return turn
    axis_turn = (second - first) % 180
    disagreement = abs((turn - axis_turn + 90) % 180 - 90)
    return turn if disagreement <= tolerance_deg else None


def _head(region: Region) -> str:
    words = region.names.get("name", "").split()
    return words[-1] if words else ""


def _touches(a: Box, b: Box, reach_m: float) -> bool:
    return footprint_gap(a, b) <= reach_m


def _belongs(region: Region, host: Region, points: np.ndarray, reach_m: float) -> bool:
    """A piece of the same kind touching the host, or a piece under its footprint that does not rest on top of it.

    Something lying on the host's top is a different thing set down on it, such as a lamp
    on a table that also moved, and is reported on its own.
    """
    if _head(host) == _head(region) and _touches(host.box, region.box, reach_m):
        return True
    piece = points[region.point_ids]
    if float(np.median(piece[:, 2])) > _top(host.box) + ON_TOP_M:
        return False
    footprint = Box(host.box.center, np.array([*host.box.size[:2], 100.0]), host.box.yaw)
    return float(inside_box(piece, footprint, margin_m=0.05).mean()) >= 0.5


def _grown(old: Box, refit: Box) -> Box:
    bottom = min(_bottom(old), _bottom(refit))
    top = _top(refit)
    return Box(np.array([*refit.center[:2], (bottom + top) / 2]), np.array([*refit.size[:2], top - bottom]), refit.yaw)


def absorb_fragments(moves: list[Move], removed: list[Region], added: list[Region], points: np.ndarray,
                     reach_m: float = 0.1) -> tuple[list[Region], list[Region]]:
    """Fold a stray piece of a moved object back into the move instead of reporting it on its own.

    One chair can come out as two regions at its old spot when its legs and seat are seen from
    different frames. An unpaired region joins an end of a move when it touches that end and has
    the same kind of name, or when most of it lies under that end's footprint whatever it is
    called, like a chair's base below its seat. Its points refit the box, which keeps the floor
    it already stood on; the rest are returned untouched.
    """
    def fold(regions: list[Region], end: str) -> list[Region]:
        left = []
        for region in regions:
            host = next((getattr(m, end) for m in moves if _belongs(region, getattr(m, end), points, reach_m)), None)
            if host is None:
                left.append(region)
                continue
            host.point_ids = np.union1d(host.point_ids, region.point_ids)
            host.box = _grown(host.box, fit_box(points[host.point_ids]))
        return left

    loose = fold(removed, "removed"), fold(added, "added")
    for move in moves:
        move.distance_m = float(np.linalg.norm(move.added.box.center[:2] - move.removed.box.center[:2]))
    return loose


def _bottom(box: Box) -> float:
    return float(box.center[2] - box.size[2] / 2)


def _top(box: Box) -> float:
    return float(box.center[2] + box.size[2] / 2)


def match_heights(moves: list[Move], same_top_m: float = 0.1, floating_m: float = 0.2) -> None:
    """Both ends of a move are one object, so when one end's box lost its legs it borrows the other's height.

    A stool whose thin legs one video never resolved comes out as a seat hanging in the air.
    The tops agreeing is what separates that from a box lifted onto a table, whose top rises too.
    """
    for move in moves:
        low, high = sorted((move.removed.box, move.added.box), key=_bottom)
        if abs(_top(low) - _top(high)) > same_top_m or _bottom(high) - _bottom(low) <= floating_m:
            continue
        bottom, top = _bottom(low), _top(high)
        high.center = np.array([high.center[0], high.center[1], (bottom + top) / 2])
        high.size = np.array([high.size[0], high.size[1], top - bottom])


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
            turn = consistent_turn(estimate_turn(points[a.point_ids], points[b.point_ids]), a.box, b.box)
            distance = float(np.linalg.norm(b.box.center[:2] - a.box.center[:2]))
            moves.append(Move(a, b, distance, turn, float(scores[i, j])))
    return moves
