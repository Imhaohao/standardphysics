"""Bounded Astra reconstruction for a measured RoomPlan graph.

The model may suggest labels and movability. It never changes geometry, node
identity, confirmation quality, or a lock already set by RoomPlan or an owner.
"""

from __future__ import annotations

import json
import os
import base64
import io
import math
import pathlib
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Literal, Sequence
from uuid import UUID

from standardphysics_contracts import DisplayAppearance, SceneGraph, SceneNode

from .coords import transform_from_arkit
from .footprints import footprint, gap_between
from .ingest import FIXED_CATEGORIES

API_KEY_ENV = "OPENROUTER_API_KEY"
MODEL_ENV = "OPENROUTER_MODEL"
BASE_URL_ENV = "OPENROUTER_BASE_URL"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-6-astra"
PROVIDER_ROUTING = {"order": ["openai"], "allow_fallbacks": False, "data_collection": "deny"}
REQUEST_TIMEOUT_SECONDS = 30.0

# A label request should carry enough visual evidence to disambiguate a box,
# without turning a four minute capture into a video upload.  These limits are
# applied after image validation and orientation normalization.
MAX_IMAGE_COUNT = 6
MAX_IMAGE_DIMENSION = 1024
MAX_IMAGE_BYTES = 2_000_000
IMAGE_JPEG_QUALITIES = (82, 72, 62, 52)
_FRAME_NUMBER = re.compile(r"frame[-_](\d+)", re.IGNORECASE)

QualityName = Literal["measured", "needs_another_look", "confirmed"]
ReconstructionSource = Literal["astra", "roomplan"]
Transport = Callable[[str, dict, dict[str, str]], dict]

COUNTER_LABELS = frozenset({"ordering counter", "service counter", "counter", "checkout counter", "cash wrap", "register counter", "sales counter"})
COUNTER_HEIGHT = (0.80, 1.40)
COUNTER_LENGTH = 2.2
WALL_GAP_METERS = 0.45
OVERLAP_METERS = 0.02
THIN_METERS = 0.04

INSTRUCTION = (
    "Label every supplied object in this shop scan with an ordinary name such as "
    "Ordering counter, Display case, Table, or Chair. Counters and plumbed-in "
    "fixtures are not movable. Do not change sizes. Mark thin or overlapping "
    "detections as needs_another_look. Return every object exactly once."
)
LABEL_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["nodes"],
    "properties": {"nodes": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "label", "movable", "quality"],
        "properties": {
            "id": {"type": "string"}, "label": {"type": "string"},
            "movable": {"type": "boolean"},
            "quality": {"type": "string", "enum": ["measured", "needs_another_look"]},
            "appearance": {
                "type": "object", "additionalProperties": False,
                "required": ["base_color", "material"],
                "properties": {
                    "base_color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                    "material": {"type": "string", "enum": ["paint", "wood", "fabric", "metal", "stone", "glass", "neutral"]},
                    "source": {"type": "string", "enum": ["astra"]},
                },
            },
        },
    }}},
}


@dataclass(frozen=True)
class LabelPatch:
    node_id: UUID
    label: str
    movable: bool
    quality: QualityName
    appearance: DisplayAppearance | None = None


@dataclass(frozen=True)
class ReconstructionResult:
    """The graph plus the label source used for this reconstruction."""

    graph: SceneGraph
    source: ReconstructionSource

    @property
    def used_model(self) -> bool:
        return self.source == "astra"


def reconstruct(
    graph: SceneGraph,
    *,
    transport: Transport | None = None,
    frame_paths: Iterable[pathlib.Path] | None = None,
    poses_path: pathlib.Path | None = None,
) -> SceneGraph:
    """Return the safe reconstructed graph for pipeline callers."""
    return reconstruct_result(
        graph, transport=transport, frame_paths=frame_paths, poses_path=poses_path
    ).graph


def reconstruct_result(
    graph: SceneGraph,
    *,
    transport: Transport | None = None,
    frame_paths: Iterable[pathlib.Path] | None = None,
    poses_path: pathlib.Path | None = None,
) -> ReconstructionResult:
    """Expose whether labels came from Astra or the deterministic local fallback."""
    remote = _remote_patches(
        graph, transport, frame_paths=frame_paths, poses_path=poses_path
    )
    if remote is None:
        return ReconstructionResult(apply_patches(graph, local_patches(graph)), "roomplan")
    local = apply_patches(graph, local_patches(graph))
    return ReconstructionResult(apply_patches(local, remote, source="astra"), "astra")


def propose_patches(
    graph: SceneGraph,
    *,
    transport: Transport | None = None,
    frame_paths: Iterable[pathlib.Path] | None = None,
    poses_path: pathlib.Path | None = None,
) -> list[LabelPatch]:
    """Return remote patches only when the complete model response is valid."""
    return _remote_patches(
        graph, transport, frame_paths=frame_paths, poses_path=poses_path
    ) or local_patches(graph)


def apply_patches(
    graph: SceneGraph, patches: list[LabelPatch], *, source: ReconstructionSource = "roomplan"
) -> SceneGraph:
    """A patch cannot resize, remove, invent, or unlock a node."""
    by_id = {patch.node_id: patch for patch in patches}
    return graph.model_copy(update={"nodes": [_apply_one(node, by_id.get(node.id), source) for node in graph.nodes]})


def local_patches(graph: SceneGraph) -> list[LabelPatch]:
    walls = [node for node in graph.nodes if node.kind == "wall"]
    objects = [node for node in graph.nodes if node.kind == "object"]
    return [_local_patch(node, walls, objects, graph) for node in graph.nodes]


def _apply_one(node: SceneNode, patch: LabelPatch | None, source: ReconstructionSource) -> SceneNode:
    if patch is None:
        return node
    if node.labeled_by == "owner" or node.quality == "confirmed":
        return node
    update: dict[str, Any] = {
        "label": patch.label or node.label,
        "movable": _locked_movable(node, patch.movable),
        "quality": node.quality if node.quality == "needs_another_look" else patch.quality,
    }
    if source == "astra":
        update["labeled_by"] = "astra"
        if patch.appearance is not None:
            update["appearance"] = patch.appearance
    return node.model_copy(update=update)


def _locked_movable(node: SceneNode, proposed: bool) -> bool:
    if node.kind != "object" or node.raw_category in FIXED_CATEGORIES:
        return False
    if not node.movable:
        return False
    return proposed


def _local_patch(node: SceneNode, walls: list[SceneNode], objects: list[SceneNode], graph: SceneGraph) -> LabelPatch:
    label, movable = _local_identity(node, walls, graph)
    return LabelPatch(node.id, label, movable, _local_quality(node, objects))


def _local_identity(node: SceneNode, walls: list[SceneNode], graph: SceneGraph) -> tuple[str, bool]:
    if node.kind == "door":
        return _door_label(node, graph), False
    if node.kind != "object" or node.raw_category in FIXED_CATEGORIES:
        return node.label, False
    if node.label.strip().casefold() in COUNTER_LABELS:
        return node.label, False
    if _looks_like_counter(node, walls):
        return "Ordering counter", False
    return _named_furniture(node.raw_category) or (node.label, node.movable)


def _named_furniture(category: str) -> tuple[str, bool] | None:
    return {
        "storage": ("Display case", True), "chair": ("Chair", True), "table": ("Table", True),
        "sofa": ("Sofa", True), "stool": ("Stool", True), "bench": ("Bench", True),
    }.get(category)


def _door_label(node: SceneNode, graph: SceneGraph) -> str:
    doors = [item for item in graph.nodes if item.kind == "door"]
    return "Front door" if len(doors) == 1 and node.label.strip().casefold() == "door" else node.label


def _looks_like_counter(node: SceneNode, walls: list[SceneNode]) -> bool:
    return (
        node.raw_category in {"storage", "table", "counter"}
        and COUNTER_HEIGHT[0] <= node.dimensions.z <= COUNTER_HEIGHT[1]
        and max(node.dimensions.x, node.dimensions.y) >= COUNTER_LENGTH
        and any(gap_between(footprint(node), footprint(wall)) <= WALL_GAP_METERS for wall in walls)
    )


def _local_quality(node: SceneNode, objects: list[SceneNode]) -> QualityName:
    if node.quality == "confirmed" or node.kind != "object":
        return node.quality
    if min(node.dimensions.x, node.dimensions.y, node.dimensions.z) < THIN_METERS:
        return "needs_another_look"
    if any(gap_between(footprint(node), footprint(other)) < OVERLAP_METERS for other in objects if other.id != node.id):
        return "needs_another_look"
    return node.quality


def _remote_patches(
    graph: SceneGraph,
    transport: Transport | None,
    *,
    frame_paths: Iterable[pathlib.Path] | None = None,
    poses_path: pathlib.Path | None = None,
) -> list[LabelPatch] | None:
    api_key = os.environ.get(API_KEY_ENV)
    if transport is None and not api_key:
        return None
    try:
        payload = (transport or _openrouter_post)(
            _chat_url(),
            _chat_body(graph, frame_paths=frame_paths, poses_path=poses_path),
            _chat_headers(api_key or ""),
        )
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, ValueError):
        return None
    return _patches_from_model(payload, graph)


def _chat_url() -> str:
    return f"{(os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip('/')}/chat/completions"


def _chat_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _chat_body(
    graph: SceneGraph,
    *,
    frame_paths: Iterable[pathlib.Path] | None = None,
    poses_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    content: str | list[dict[str, Any]] = json.dumps(_context(graph))
    image_messages = _image_messages(graph, frame_paths, poses_path)
    if image_messages:
        content = [{"type": "text", "text": content}, *image_messages]
    return {
        "model": os.environ.get(MODEL_ENV) or DEFAULT_MODEL,
        "messages": [{"role": "system", "content": INSTRUCTION}, {"role": "user", "content": content}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "astra_labels", "strict": True, "schema": LABEL_SCHEMA}},
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
    return {"id": str(node.id), "kind": node.kind, "label": node.label, "x": round(position.x, 3), "y": round(position.y, 3), "length": round(max(node.dimensions.x, node.dimensions.y), 3)}


def _object_brief(node: SceneNode) -> dict[str, Any]:
    position = node.transform.position
    return {
        "id": str(node.id), "raw_category": node.raw_category, "label": node.label,
        "width": round(node.dimensions.x, 3), "depth": round(node.dimensions.y, 3), "height": round(node.dimensions.z, 3),
        "x": round(position.x, 3), "y": round(position.y, 3), "movable": node.movable,
    }


def _openrouter_post(url: str, body: dict, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
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
    items = parsed.get("nodes") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return None
    expected = {node.id for node in graph.nodes if node.kind == "object"}
    if not expected:
        return None
    patches = [_patch_from_item(item, expected) for item in items]
    if any(patch is None for patch in patches):
        return None
    found = [patch for patch in patches if patch is not None]
    return found if {patch.node_id for patch in found} == expected and len(found) == len(expected) else None


def _message_content(payload: dict) -> str | None:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    return content if isinstance(content, str) else None


def _patch_from_item(item: object, expected: set[UUID]) -> LabelPatch | None:
    if not isinstance(item, dict):
        return None
    try:
        node_id = UUID(str(item.get("id")))
    except (ValueError, TypeError):
        return None
    label, quality, movable = item.get("label"), item.get("quality"), item.get("movable")
    if node_id not in expected or not isinstance(label, str) or not label.strip() or quality not in {"measured", "needs_another_look"} or not isinstance(movable, bool):
        return None
    return LabelPatch(node_id, label.strip()[:80], movable, quality)
