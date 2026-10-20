"""Predicates over measured regions, written as data and evaluated here.

A relation a model coins carries the predicate that justifies it, so anything
that needs the truth re-runs the predicate instead of trusting the relation's
name. A predicate is a small tree:

    {"all": [p, ...]}   every one holds
    {"any": [p, ...]}   at least one holds
    {"not": p}          p does not hold
    {"op": "gap", "a": "$from", "b": "$to", "along": "down", "under": 0.05}

A leaf takes one substrate measurement and compares it with `under`, `over`, or
both. `a` and `b` name a region: `$from` and `$to` are the two ends of the
relation being judged, and anything else is a region's id. `along` is `down`,
the direction the phone measured gravity in, `up`, or three numbers.

The language has no loops, no names and no way out of this module, so the worst a
written predicate can do is be wrong; it cannot run long or reach anything.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from ..substrate.regions import (
    Region,
    adjacency,
    centroid,
    extent_along,
    footprint_overlap,
    gap,
    overlap_fraction,
    separation,
    volume,
)

MAX_DEPTH = 8
MAX_BRANCHES = 16


class PredicateError(ValueError):
    """A predicate that is not written in the language: refused before anything is measured."""


@dataclass(frozen=True)
class Scope:
    """What a predicate is evaluated against."""

    regions: Mapping[str, Region]
    down: np.ndarray
    bound: Mapping[str, str]
    """`$from` and `$to`, each to the id of the region it stands for."""

    def region(self, name: object) -> Region:
        if not isinstance(name, str):
            raise PredicateError(f"a region is named by a string, not {name!r}")
        key = self.bound.get(name, name)
        if key not in self.regions:
            raise PredicateError(f"no region {name!r} in this scan")
        return self.regions[key]

    def direction(self, along: object) -> np.ndarray:
        if along == "down":
            return self.down
        if along == "up":
            return -self.down
        if isinstance(along, list) and len(along) == 3 and all(isinstance(value, int | float) for value in along):
            vector = np.asarray(along, dtype=np.float64)
            if np.linalg.norm(vector) > 1e-9:
                return vector / np.linalg.norm(vector)
        raise PredicateError(f"`along` is down, up or three numbers, not {along!r}")


def _pair(measure: Callable[[Region, Region, Scope, dict], float]):
    return lambda leaf, scope: measure(scope.region(leaf.get("a")), scope.region(leaf.get("b")), scope, leaf)


def _span(region: Region, along: np.ndarray) -> float:
    low, high = extent_along(region, along)
    return high - low


MEASUREMENTS: dict[str, tuple[frozenset[str], Callable[[dict, Scope], float]]] = {
    "gap": (frozenset({"a", "b", "along"}), _pair(lambda a, b, s, leaf: gap(a, b, s.direction(leaf.get("along"))))),
    "overlap_fraction": (frozenset({"a", "b"}), _pair(lambda a, b, s, leaf: overlap_fraction(a, b))),
    "footprint_overlap": (
        frozenset({"a", "b", "along"}),
        _pair(lambda a, b, s, leaf: footprint_overlap(a, b, s.direction(leaf.get("along")))),
    ),
    "contact_area": (frozenset({"a", "b"}), _pair(lambda a, b, s, leaf: adjacency(a, b).area)),
    "separation": (frozenset({"a", "b"}), _pair(lambda a, b, s, leaf: separation(a, b)[0])),
    "rise": (
        frozenset({"a", "b", "along"}),
        _pair(lambda a, b, s, leaf: float((centroid(a) - centroid(b)) @ s.direction(leaf.get("along")))),
    ),
    "extent": (frozenset({"a", "along"}), lambda leaf, s: _span(s.region(leaf.get("a")), s.direction(leaf.get("along")))),
    "volume": (frozenset({"a"}), lambda leaf, s: volume(s.region(leaf.get("a")))),
}
"""Each measurement a leaf may take: the arguments it needs, and how it is taken."""

COMPARISONS = frozenset({"under", "over"})


def holds(predicate: object, scope: Scope, depth: int = 0) -> bool:
    """Whether the predicate is true of the measured regions. A predicate outside the language raises."""
    if depth > MAX_DEPTH:
        raise PredicateError(f"a predicate may nest at most {MAX_DEPTH} deep")
    if not isinstance(predicate, dict):
        raise PredicateError(f"a predicate is an object, not {predicate!r}")
    if "op" in predicate:
        return _leaf_holds(predicate, scope)
    return _branch_holds(predicate, scope, depth)


def measured(leaf: dict, scope: Scope) -> float:
    """The value a leaf's measurement takes, before it is compared with anything."""
    op = leaf.get("op")
    if op not in MEASUREMENTS:
        raise PredicateError(f"no measurement {op!r}; there are {sorted(MEASUREMENTS)}")
    needs, take = MEASUREMENTS[op]
    extra = set(leaf) - needs - COMPARISONS - {"op"}
    missing = needs - set(leaf)
    if extra or missing:
        raise PredicateError(f"{op} takes {sorted(needs)}; got extra {sorted(extra)}, missing {sorted(missing)}")
    return float(take(leaf, scope))


def _leaf_holds(leaf: dict, scope: Scope) -> bool:
    limits = {key: leaf[key] for key in COMPARISONS if key in leaf}
    if not limits or not all(isinstance(value, int | float) for value in limits.values()):
        raise PredicateError("a measurement is compared with a number under `under`, `over`, or both")
    value = measured(leaf, scope)
    return value < limits.get("under", np.inf) and value > limits.get("over", -np.inf)


def _branch_holds(branch: dict, scope: Scope, depth: int) -> bool:
    if len(branch) != 1:
        raise PredicateError(f"a combination has one key, all, any or not, not {sorted(branch)}")
    (kind, parts), = branch.items()
    if kind == "not":
        return not holds(parts, scope, depth + 1)
    if kind not in ("all", "any") or not isinstance(parts, list) or not 0 < len(parts) <= MAX_BRANCHES:
        raise PredicateError(f"{kind!r} takes a list of 1 to {MAX_BRANCHES} predicates")
    results = [holds(part, scope, depth + 1) for part in parts]
    return all(results) if kind == "all" else any(results)
