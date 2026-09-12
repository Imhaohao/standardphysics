"""One fingerprint for a layout, so every lane means the same thing by it.

An assessment records the layout it judged and a proposal records the layout it
was built against. Both have to agree, or a stale result can recolour geometry
that has already moved on. The fingerprint covers what a check depends on: each
node's identity, kind, transform, dimensions, movability and quality, rounded to
a micrometre. Node order, the revision number and labels do not count.
"""

from __future__ import annotations

import hashlib
import json

from .scene import SceneGraph, SceneNode

PRECISION = 6


def _node_fingerprint(node: SceneNode) -> list:
    dims = node.dimensions
    return [
        str(node.id),
        node.kind,
        [round(value, PRECISION) for value in node.transform.m],
        [round(dims.x, PRECISION), round(dims.y, PRECISION), round(dims.z, PRECISION)],
        node.movable,
        node.quality,
    ]


def graph_hash(graph: SceneGraph) -> str:
    payload = sorted((_node_fingerprint(node) for node in graph.nodes), key=str)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
