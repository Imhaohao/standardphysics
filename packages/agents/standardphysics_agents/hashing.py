"""One canonical fingerprint for a layout.

An assessment records the layout it judged and a proposal records the layout it
was built against. Both have to agree, or a stale result can recolour geometry
that has already moved on, so the fingerprint is computed in exactly one place.
"""

from __future__ import annotations

import hashlib
import json

from standardphysics_contracts import SceneGraph


def _node_fingerprint(node) -> list:
    return [
        str(node.id),
        node.kind,
        [round(value, 6) for value in node.transform.m],
        [round(node.dimensions.x, 6), round(node.dimensions.y, 6), round(node.dimensions.z, 6)],
        node.movable,
        node.quality,
    ]


def graph_hash(graph: SceneGraph) -> str:
    payload = sorted((_node_fingerprint(node) for node in graph.nodes), key=str)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def inventory(graph: SceneGraph) -> dict[str, int]:
    """How many of each thing the owner has. Placement is adjustable; this is not."""
    counts: dict[str, int] = {}
    for node in graph.nodes:
        if node.kind != "object":
            continue
        counts[node.label] = counts.get(node.label, 0) + 1
    return counts
