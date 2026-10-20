"""Things in the room: what the photos and the scanner named, each wearing the surface the mesh measured for it.

Discovery reads the photos and carves a box for every object they agree on,
across views and with the people taken out, and the scanner boxes what it
knows. Those boxes are where things are and what they were called. The mesh,
cut into pieces by `substrate.segment`, is what they are made of: a piece that
lies inside a thing's box is part of that thing. The box stays the thing's
region: a piece may reach a little outside it, and fitting the region to whole
pieces stretched a wall into a slab four cubic metres thick.

A piece inside two boxes belongs to the smaller, so a cup on a table is the
cup's. A piece inside none is matter nobody named, and stays a bare region.

The name is whatever discovery or the scanner wrote, kept as a free string.
Nothing here compares it to a list, and nothing above this layer may branch on it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import numpy as np
from standardphysics_contracts import SceneGraph

from ..substrate.regions import Region, contains, region_of, volume
from ..substrate.segment import Piece
from ..textures.regions import VertexIndex

INSIDE_SHARE = 0.6
"""Share of a piece's surface that must lie in a thing's box for the piece to be part of it."""

BOX_REACH = 0.03
"""Metres a box is grown by before pieces are tested against it: a phone's box misses its surface by about this."""


@dataclass(frozen=True)
class Entity:
    """A named thing, made of pieces of the measured surface."""

    id: uuid.UUID
    """The scene node it was named as, so a relation stays attached across processing runs."""

    name: str
    pieces: tuple[uuid.UUID, ...]
    region: Region
    """The box it was measured as."""


def coin_entities(pieces: list[Piece], graph: SceneGraph) -> list[Entity]:
    """Every named thing in the scan, each with the pieces of the mesh that lie inside it."""
    owner = _owners(pieces, graph)
    return [_entity(node, [pieces[index] for index in np.flatnonzero(owner == place)])
            for place, node in enumerate(graph.nodes)]


def _owners(pieces: list[Piece], graph: SceneGraph) -> np.ndarray:
    """For each piece, the index of the smallest node it lies inside, or -1."""
    points = np.concatenate([piece.points for piece in pieces]) if pieces else np.empty((0, 3))
    which = np.repeat(np.arange(len(pieces)), [len(piece.points) for piece in pieces])
    sizes = np.bincount(which, minlength=len(pieces))
    index = VertexIndex(points)
    owner = np.full(len(pieces), -1, dtype=np.int64)
    smallest_first = sorted(range(len(graph.nodes)), key=lambda place: volume(region_of(graph.nodes[place])))
    for place in smallest_first:
        box = _grown(region_of(graph.nodes[place]))
        near = index.within(*_bounds(box))
        inside = np.bincount(which[near[contains(box, points[near])]], minlength=len(pieces))
        owner[(owner < 0) & (inside >= INSIDE_SHARE * np.maximum(sizes, 1))] = place
    return owner


def _grown(region: Region) -> Region:
    return Region(id=region.id, pose=region.pose, extents=region.extents + 2 * BOX_REACH, markings=region.markings)


def _bounds(region: Region) -> tuple[np.ndarray, np.ndarray]:
    reach = np.abs(region.rotation) @ (region.extents / 2)
    return region.centre - reach - 1e-6, region.centre + reach + 1e-6


def _entity(node, members: list[Piece]) -> Entity:
    return Entity(id=node.id, name=node.label, pieces=tuple(piece.region.id for piece in members), region=region_of(node))
