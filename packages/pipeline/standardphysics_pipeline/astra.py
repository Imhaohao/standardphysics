"""Astra labels and cleans a scanned room. It never writes dimensions.

OpenRouter is the live path (`openai/gpt-6-astra` by default). With no key the
same patch list is produced by the local shop heuristics, so ingest still
returns an object-separated graph the simulator can click and move.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Literal
from uuid import UUID

from standardphysics_contracts import SceneGraph, SceneNode

from .footprints import footprint, gap_between
from .ingest import FIXED_CATEGORIES

API_KEY_ENV = "OPENROUTER_API_KEY"
MODEL_ENV = "OPENROUTER_MODEL"
BASE_URL_ENV = "OPENROUTER_BASE_URL"

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-6-astra"

PROVIDER_ROUTING = {
    "order": ["openai"],
    "allow_fallbacks": False,
    "data_collection": "deny",
}

REQUEST_TIMEOUT_SECONDS = 30.0

QualityName = Literal["measured", "needs_another_look", "confirmed"]

COUNTER_LABELS = frozenset(
    {
        "ordering counter",
        "service counter",
        "counter",
        "checkout counter",
        "cash wrap",
        "register counter",
        "sales counter",
    }
)

COUNTER_HEIGHT = (0.80, 1.40)
COUNTER_LENGTH = 2.2
WALL_GAP_METERS = 0.45
OVERLAP_METERS = 0.02
THIN_METERS = 0.04

INSTRUCTION = (
    "Label each object in this shop scan. Use ordinary names such as "
    "Ordering counter, Display case, Table, or Chair. Counters and plumbed-in "
    "fixtures are not movable. Do not change sizes. Mark thin or overlapping "
    "detections as needs_another_look."
)

LABEL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["nodes"],
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "label", "movable", "quality"],
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "movable": {"type": "boolean"},
                    "quality": {
                        "type": "string",
                        "enum": ["measured", "needs_another_look"],
                    },
                },
            },
        }
    },
}

Transport = Callable[[str, dict, dict[str, str]], dict]


@dataclass(frozen=True)
class LabelPatch:
    node_id: UUID
    label: str
    movable: bool
    quality: QualityName


def reconstruct(graph: SceneGraph, *, transport: Transport | None = None) -> SceneGraph:
    """Label and clean. Dimensions, IDs and occupancy stay as ingest wrote them."""
    return apply_patches(graph, propose_patches(graph, transport=transport))


def propose_patches(
    graph: SceneGraph, *, transport: Transport | None = None
) -> list[LabelPatch]:
    remote = _remote_patches(graph, transport)
    return remote if remote is not None else local_patches(graph)


def apply_patches(graph: SceneGraph, patches: list[LabelPatch]) -> SceneGraph:
    """Apply labels and flags. A patch cannot resize, delete, or invent a node."""
    by_id = {patch.node_id: patch for patch in patches}
    nodes = [_apply_one(node, by_id.get(node.id)) for node in graph.nodes]
    return graph.model_copy(update={"nodes": nodes})


def local_patches(graph: SceneGraph) -> list[LabelPatch]:
    walls = [node for node in graph.nodes if node.kind == "wall"]
    objects = [node for node in graph.nodes if node.kind == "object"]
    return [_local_patch(node, walls, objects, graph) for node in graph.nodes]


def _apply_one(node: SceneNode, patch: LabelPatch | None) -> SceneNode:
    if patch is None:
        return node
    return node.model_copy(
        update={
            "label": patch.label or node.label,
            "movable": _locked_movable(node, patch.movable),
            "quality": node.quality if node.quality == "confirmed" else patch.quality,
            "labeled_by": "astra",
        }
    )


def _locked_movable(node: SceneNode, proposed: bool) -> bool:
    if node.kind != "object" or node.raw_category in FIXED_CATEGORIES:
        return False
    return proposed


def _local_patch(
    node: SceneNode,
    walls: list[SceneNode],
    objects: list[SceneNode],
    graph: SceneGraph,
) -> LabelPatch:
    label, movable = _local_identity(node, walls, graph)
    return LabelPatch(
        node_id=node.id,
        label=label,
        movable=movable,
        quality=_local_quality(node, objects),
    )


def _local_identity(
    node: SceneNode, walls: list[SceneNode], graph: SceneGraph
) -> tuple[str, bool]:
    if node.kind == "door":
        return _door_label(node, graph), False
    if node.kind != "object":
        return node.label, False
    if node.raw_category in FIXED_CATEGORIES:
        return node.label, False
    if node.label.strip().casefold() in COUNTER_LABELS:
        return node.label, False
    if _looks_like_counter(node, walls):
        return "Ordering counter", False
    named = _named_furniture(node.raw_category)
    if named is not None:
        return named
    return node.label, node.movable


def _named_furniture(category: str) -> tuple[str, bool] | None:
    names = {
        "storage": ("Display case", True),
        "chair": ("Chair", True),
        "table": ("Table", True),
        "sofa": ("Sofa", True),
        "stool": ("Stool", True),
        "bench": ("Bench", True),
    }
    return names.get(category)


def _door_label(node: SceneNode, graph: SceneGraph) -> str:
    doors = [item for item in graph.nodes if item.kind == "door"]
    if len(doors) == 1 and node.label.strip().casefold() == "door":
        return "Front door"
    return node.label


def _looks_like_counter(node: SceneNode, walls: list[SceneNode]) -> bool:
    if node.raw_category not in {"storage", "table", "counter"}:
        return False
    height = node.dimensions.z
    if height < COUNTER_HEIGHT[0] or height > COUNTER_HEIGHT[1]:
        return False
    if max(node.dimensions.x, node.dimensions.y) < COUNTER_LENGTH:
        return False
    return any(
        gap_between(footprint(node), footprint(wall)) <= WALL_GAP_METERS
        for wall in walls
    )


def _local_quality(node: SceneNode, objects: list[SceneNode]) -> QualityName:
    if node.quality == "confirmed" or node.kind != "object":
        return node.quality
    extents = (node.dimensions.x, node.dimensions.y, node.dimensions.z)
    if min(extents) < THIN_METERS:
        return "needs_another_look"
    if any(_overlaps(node, other) for other in objects if other.id != node.id):
        return "needs_another_look"
    return node.quality


def _overlaps(left: SceneNode, right: SceneNode) -> bool:
    return gap_between(footprint(left), footprint(right)) < OVERLAP_METERS


def _remote_patches(
    graph: SceneGraph, transport: Transport | None
) -> list[LabelPatch] | None:
    api_key = os.environ.get(API_KEY_ENV)
    if transport is None and not api_key:
        return None
    try:
        payload = (transport or _openrouter_post)(
            _chat_url(),
            _chat_body(graph),
            _chat_headers(api_key or ""),
        )
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, ValueError):
        return None
    return _patches_from_model(payload, graph)


def _chat_url() -> str:
    base = os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL
    return f"{base.rstrip('/')}/chat/completions"


def _chat_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _chat_body(graph: SceneGraph) -> dict[str, Any]:
    model = os.environ.get(MODEL_ENV) or DEFAULT_MODEL
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": INSTRUCTION},
            {"role": "user", "content": json.dumps(_context(graph))},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "astra_labels",
                "strict": True,
                "schema": LABEL_SCHEMA,
            },
        },
        "provider": PROVIDER_ROUTING,
    }


def _context(graph: SceneGraph) -> dict[str, Any]:
    return {
        "walls": [_surface_brief(node) for node in graph.nodes if node.kind == "wall"],
        "objects": [_object_brief(node) for node in graph.nodes if node.kind == "object"],
        "doors": [_surface_brief(node) for node in graph.nodes if node.kind == "door"],
    }


def _surface_brief(node: SceneNode) -> dict[str, Any]:
    position = node.transform.position
    return {
        "id": str(node.id),
        "kind": node.kind,
        "label": node.label,
        "x": round(position.x, 3),
        "y": round(position.y, 3),
        "length": round(max(node.dimensions.x, node.dimensions.y), 3),
    }


def _object_brief(node: SceneNode) -> dict[str, Any]:
    position = node.transform.position
    return {
        "id": str(node.id),
        "raw_category": node.raw_category,
        "label": node.label,
        "width": round(node.dimensions.x, 3),
        "depth": round(node.dimensions.y, 3),
        "height": round(node.dimensions.z, 3),
        "x": round(position.x, 3),
        "y": round(position.y, 3),
        "movable": node.movable,
    }


def _openrouter_post(url: str, body: dict, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        parsed = json.loads(response.read())
    if not isinstance(parsed, dict):
        raise ValueError("openrouter_not_an_object")
    return parsed


def _patches_from_model(payload: dict, graph: SceneGraph) -> list[LabelPatch] | None:
    content = _message_content(payload)
    if content is None:
        return None
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    nodes = parsed.get("nodes") if isinstance(parsed, dict) else None
    if not isinstance(nodes, list):
        return None
    known = {node.id for node in graph.nodes}
    patches = [_patch_from_item(item, known) for item in nodes]
    found = [patch for patch in patches if patch is not None]
    return found or None


def _message_content(payload: dict) -> str | None:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    return content if isinstance(content, str) else None


def _patch_from_item(item: object, known: set[UUID]) -> LabelPatch | None:
    if not isinstance(item, dict):
        return None
    try:
        node_id = UUID(str(item.get("id")))
    except (ValueError, TypeError):
        return None
    if node_id not in known:
        return None
    label = item.get("label")
    quality = item.get("quality")
    if not isinstance(label, str) or not label.strip():
        return None
    if quality not in {"measured", "needs_another_look"}:
        return None
    if not isinstance(item.get("movable"), bool):
        return None
    return LabelPatch(
        node_id=node_id,
        label=label.strip()[:80],
        movable=item["movable"],
        quality=quality,
    )
