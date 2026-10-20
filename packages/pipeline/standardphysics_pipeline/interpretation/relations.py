"""Relations between things, each carrying the predicate that justifies it.

A relation is a name a model coined for an edge between two things, such as
"rests on", and a predicate over the substrate that says when the edge holds.
The name is for showing a person. Anything that needs to know whether the edge
holds runs the predicate, which is why one whose predicate fails on the regions
it names is never kept.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from ..substrate.regions import Region, adjacency, centroid, footprint_overlap, gap, separation, volume
from .entities import Entity
from .predicates import PredicateError, Scope, holds

NEAR = 0.05
"""Metres two things may stand apart and still be offered to a model as a pair worth naming."""


@dataclass(frozen=True)
class Relation:
    name: str
    """What the model called the edge, as it wrote it."""

    source: uuid.UUID
    target: uuid.UUID
    because: dict
    """The predicate, with `$from` for `source` and `$to` for `target`."""


def still_holds(relation: Relation, regions: dict[str, Region], down: np.ndarray) -> bool:
    """Whether the relation's own predicate is true of the regions it names; a malformed predicate is not."""
    scope = Scope(regions, down, {"$from": str(relation.source), "$to": str(relation.target)})
    try:
        return holds(relation.because, scope)
    except PredicateError:
        return False


def kept(relations: Iterable[Relation], entities: list[Entity], down: np.ndarray) -> list[Relation]:
    """The relations whose predicates hold, once each: a model's claim is evaluated, not believed."""
    regions = {str(entity.id): entity.region for entity in entities}
    seen: set[tuple] = set()
    out = []
    for relation in relations:
        key = (relation.name.lower(), relation.source, relation.target)
        known = str(relation.source) in regions and str(relation.target) in regions
        if key not in seen and known and relation.source != relation.target and still_holds(relation, regions, down):
            seen.add(key)
            out.append(relation)
    return out


def neighbours(entities: list[Entity], within: float = NEAR) -> list[tuple[Entity, Entity]]:
    """Every pair of things that touch or nearly touch, each pair once."""
    low = np.array([_low(entity.region) for entity in entities])
    high = np.array([_high(entity.region) for entity in entities])
    pairs = []
    for first in range(len(entities)):
        apart = np.maximum(low[first + 1:] - high[first], low[first] - high[first + 1:]).max(axis=1)
        for offset in np.flatnonzero(apart <= within):
            second = first + 1 + int(offset)
            if separation(entities[first].region, entities[second].region)[0] <= within:
                pairs.append((entities[first], entities[second]))
    return pairs


def facts(source: Entity, target: Entity, down: np.ndarray) -> dict:
    """What was measured between two things, for a model to name the relation from. Every figure is the engine's."""
    up = -down
    return {
        "source_bottom_above_target_top_m": round(gap(source.region, target.region, up), 3),
        "target_bottom_above_source_top_m": round(gap(target.region, source.region, up), 3),
        "source_footprint_within_target": round(footprint_overlap(source.region, target.region, up), 3),
        "target_footprint_within_source": round(footprint_overlap(target.region, source.region, up), 3),
        "contact_area_m2": round(adjacency(source.region, target.region).area, 4),
        "source_middle_above_target_middle_m": round(float((centroid(source.region) - centroid(target.region)) @ up), 3),
        "source_volume_m3": round(volume(source.region), 4),
        "target_volume_m3": round(volume(target.region), 4),
    }


def _low(region: Region) -> np.ndarray:
    return region.centre - np.abs(region.rotation) @ (region.extents / 2)


def _high(region: Region) -> np.ndarray:
    return region.centre + np.abs(region.rotation) @ (region.extents / 2)
