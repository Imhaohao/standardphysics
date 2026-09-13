"""Bounded Astra reconstruction for a measured RoomPlan graph.

The model may suggest labels and movability. It never changes geometry, node
identity, confirmation quality, or a lock already set by RoomPlan or an owner.
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator, Literal, Sequence
from uuid import UUID

from standardphysics_contracts import DisplayAppearance, SceneGraph, SceneNode

from .footprints import footprint, gap_between
from .ingest import FIXED_CATEGORIES, sleeping_places

API_KEY_ENV = "OPENROUTER_API_KEY"
MODEL_ENV = "OPENROUTER_MODEL"
PROVIDER_NAME = "openrouter"
BASE_URL_ENV = "OPENROUTER_BASE_URL"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-6-astra"
PROVIDER_ROUTING = {"order": ["openai"], "allow_fallbacks": False, "data_collection": "deny"}
REQUEST_TIMEOUT_SECONDS = 120.0

# A label request should carry enough visual evidence to disambiguate a box,
# without turning a four minute capture into a video upload.  These limits are
# applied after image validation and orientation normalization.
MAX_IMAGE_COUNT = 6
MAX_IMAGE_DIMENSION = 1024
MAX_IMAGE_BYTES = 2_000_000
MAX_SOURCE_IMAGE_BYTES = 16_000_000
MAX_SOURCE_IMAGE_PIXELS = 40_000_000
IMAGE_JPEG_QUALITIES = (82, 72, 62, 52)
_FRAME_NUMBER = re.compile(r"frame[-_](\d+)", re.IGNORECASE)
MAX_OUTPUT_TOKENS = 8_192
MAX_RESPONSE_BYTES = 2_000_000

QualityName = Literal["measured", "needs_another_look", "confirmed"]
ReconstructionSource = Literal["astra", "roomplan"]
Transport = Callable[[str, dict, dict[str, str]], dict]

COUNTER_LABELS = frozenset({"ordering counter", "service counter", "counter", "checkout counter", "cash wrap", "register counter", "sales counter"})
COUNTER_HEIGHT = (0.80, 1.40)
COUNTER_LENGTH = 2.2
WALL_GAP_METERS = 0.45
OVERLAP_METERS = 0.02
THIN_METERS = 0.04

LABELLING_RULES = (
    "Do not change sizes. Mark thin or overlapping "
    "detections as needs_another_look. You may add a display-only appearance "
    "with a six-digit base color and broad material when the frame evidence is "
    "clear; when images_provided is false, appearance must be null. Return every "
    "object exactly once."
)
INSTRUCTION = (
    "Label every supplied object in this shop scan with an ordinary name such as "
    "Ordering counter, Display case, Table, or Chair. Counters and plumbed-in "
    "fixtures are not movable. " + LABELLING_RULES
)
HOME_INSTRUCTION = (
    "Label every supplied object in this scan of a bedroom or dorm room with an "
    "ordinary name such as Bed, Desk, Dresser, Shelf, or Chair. It is a home, so "
    "nothing in it is an ordering counter, a register, or a display case. "
    "Plumbed-in fixtures are not movable. " + LABELLING_RULES
)
LABEL_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["nodes"],
    "properties": {"nodes": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "label", "movable", "quality", "appearance"],
        "properties": {
            "id": {"type": "string"}, "label": {"type": "string"},
            "movable": {"type": "boolean"},
            "quality": {"type": "string", "enum": ["measured", "needs_another_look"]},
            "appearance": {"anyOf": [
                {"type": "null"},
                {
                    "type": "object", "additionalProperties": False,
                    "required": ["base_color", "material"],
                    "properties": {
                        "base_color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                        "material": {"type": "string", "enum": ["paint", "wood", "fabric", "metal", "stone", "glass", "neutral"]},
                    },
                },
            ]},
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
    home = bool(sleeping_places(graph))
    if not home and _looks_like_counter(node, walls):
        return "Ordering counter", False
    return _named_furniture(node.raw_category, home) or (node.label, node.movable)


def _named_furniture(category: str, home: bool = False) -> tuple[str, bool] | None:
    """Plain names for RoomPlan's categories. Storage in a home is a dresser or
    a shelf, never something a shop displays stock in."""
    if home and category == "storage":
        return "Storage", True
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
    with _model_call(len(graph.nodes)) as answered:
        try:
            body = _chat_body(
                graph, frame_paths=frame_paths, poses_path=poses_path
            )
            payload = (transport or _openrouter_post)(
                _chat_url(),
                body,
                _chat_headers(api_key or ""),
            )
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, ValueError):
            return None
        patches = _patches_from_model(payload, graph, allow_appearance=_body_has_images(body))
        answered(patches, payload)
    return patches


@contextmanager
def _model_call(node_count: int) -> Iterator[Callable[[list | None, Any], None]]:
    """A Weave chat span around one Astra request, when Weave is already running.

    Weave is not a dependency of this package, and the agents lane's tracing
    helper sits above it, so this only uses a Weave that a caller has imported
    and initialized. The span holds the node count sent and the patch count
    returned: never the key, the headers, the photographs or the scan.
    """
    llm = _open_chat_span()

    def answered(patches: list | None, payload: Any) -> None:
        _record_chat(llm, node_count, patches, payload)

    try:
        yield answered
    finally:
        _close_chat_span(llm)


def _open_chat_span() -> Any:
    weave = sys.modules.get("weave")
    try:
        if weave is None or weave.get_client() is None:
            return None
        model = os.environ.get(MODEL_ENV) or DEFAULT_MODEL
        return weave.conversation.start_llm(model=model, provider_name=PROVIDER_NAME).__enter__()
    except Exception:
        return None


def _record_chat(llm: Any, node_count: int, patches: list | None, payload: Any) -> None:
    if llm is None:
        return
    usage = payload.get("usage") if isinstance(payload, dict) else None
    counts = usage if isinstance(usage, dict) else {}
    try:
        types = sys.modules["weave"].conversation
        llm.record(
            input_messages=[types.Message(role="user", content=f"{node_count} scene nodes")],
            output_messages=[
                types.Message(role="assistant", content=f"{len(patches or [])} label patches")
            ],
            usage=types.Usage(
                input_tokens=int(counts.get("prompt_tokens") or 0),
                output_tokens=int(counts.get("completion_tokens") or 0),
            ),
        )
    except Exception:
        return


def _close_chat_span(llm: Any) -> None:
    if llm is None:
        return
    try:
        llm.__exit__(None, None, None)
    except Exception:
        return


def _body_has_images(body: dict[str, Any]) -> bool:
    messages = body.get("messages") or []
    if len(messages) < 2 or not isinstance(messages[1], dict):
        return False
    content = messages[1].get("content")
    return isinstance(content, list) and any(
        isinstance(item, dict) and item.get("type") == "image_url" for item in content
    )


def _chat_url() -> str:
    return f"{(os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip('/')}/chat/completions"


def _chat_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _instruction(graph: SceneGraph) -> str:
    return HOME_INSTRUCTION if sleeping_places(graph) else INSTRUCTION


def _chat_body(
    graph: SceneGraph,
    *,
    frame_paths: Iterable[pathlib.Path] | None = None,
    poses_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    image_messages = _image_messages(graph, frame_paths, poses_path)
    content: str | list[dict[str, Any]] = json.dumps(
        _context(graph, images_provided=bool(image_messages))
    )
    if image_messages:
        content = [{"type": "text", "text": content}, *image_messages]
    return {
        "model": os.environ.get(MODEL_ENV) or DEFAULT_MODEL,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "reasoning": {"effort": "low"},
        "messages": [{"role": "system", "content": _instruction(graph)}, {"role": "user", "content": content}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "astra_labels", "strict": True, "schema": LABEL_SCHEMA}},
        "provider": PROVIDER_ROUTING,
    }


@dataclass(frozen=True)
class _PoseEvidence:
    frame_key: str
    orientation: str
    transform: tuple[float, ...]
    intrinsics: tuple[float, ...]
    order: int


@dataclass(frozen=True)
class _FrameCandidate:
    path: pathlib.Path
    score: float
    in_view: bool
    order: int


def select_keyframes(
    graph: SceneGraph,
    frame_paths: Iterable[pathlib.Path],
    poses_path: pathlib.Path | None = None,
    *,
    max_images: int = MAX_IMAGE_COUNT,
) -> list[pathlib.Path]:
    """Choose a small, deterministic set of uploaded frames for label evidence.

    When pose metadata is available, candidates are ranked by the projection of
    each object's measured centre into the camera.  A round-robin pass gives an
    object more than one view when the request has room for it; a final pass
    fills any remaining slots with the strongest candidates.  Missing or bad
    metadata falls back to evenly spaced paths, so labels still work for older
    uploads that contain only a few frame artifacts.
    """
    limit = max(0, min(int(max_images), MAX_IMAGE_COUNT))
    paths = _unique_paths(frame_paths)
    if limit == 0 or not paths:
        return []
    poses = _load_poses(poses_path)
    if not poses:
        return _spread_paths(paths, limit)

    pose_by_key = {pose.frame_key: pose for pose in poses}
    candidates = [
        _FrameCandidate(path, score, visible, order)
        for order, path in enumerate(paths)
        for score, visible in [_best_frame_score(path, graph, pose_by_key)]
    ]
    objects = [node for node in graph.nodes if node.kind == "object"]
    if not objects:
        return _strongest_paths(candidates, limit)

    rankings: list[list[_FrameCandidate]] = []
    for node in objects:
        ranked = _rank_for_object(node, paths, pose_by_key)
        rankings.append(ranked)

    selected: list[pathlib.Path] = []
    selected_paths: set[pathlib.Path] = set()
    # Two views are useful for one or two objects.  For a larger graph, give
    # each object one view first and use the remaining slots for coverage.
    views_per_object = 2 if len(objects) <= 3 else 1
    for view_number in range(views_per_object):
        for ranked in rankings:
            for candidate in ranked[view_number:]:
                if candidate.path not in selected_paths:
                    selected.append(candidate.path)
                    selected_paths.add(candidate.path)
                    break
            if len(selected) >= limit:
                return selected[:limit]

    for candidate in sorted(candidates, key=lambda item: (-item.score, item.order)):
        if candidate.path not in selected_paths:
            selected.append(candidate.path)
            selected_paths.add(candidate.path)
        if len(selected) >= limit:
            break
    return selected[:limit]


def _unique_paths(frame_paths: Iterable[pathlib.Path]) -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for raw_path in frame_paths or ():
        try:
            path = pathlib.Path(raw_path)
        except (TypeError, ValueError):
            continue
        if path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def _spread_paths(paths: Sequence[pathlib.Path], limit: int) -> list[pathlib.Path]:
    if len(paths) <= limit:
        return list(paths)
    if limit == 1:
        return [paths[0]]
    indices = {
        round(index * (len(paths) - 1) / (limit - 1))
        for index in range(limit)
    }
    return [paths[index] for index in sorted(indices)]


def _strongest_paths(candidates: Sequence[_FrameCandidate], limit: int) -> list[pathlib.Path]:
    ranked = sorted(candidates, key=lambda item: (-item.score, item.order))
    return [candidate.path for candidate in ranked[:limit]]


def _rank_for_object(
    node: SceneNode,
    paths: Sequence[pathlib.Path],
    pose_by_key: dict[str, _PoseEvidence],
) -> list[_FrameCandidate]:
    ranked: list[_FrameCandidate] = []
    for order, path in enumerate(paths):
        pose = pose_by_key.get(_frame_key(path.name))
        if pose is None:
            ranked.append(_FrameCandidate(path, -100.0, False, order))
            continue
        score, visible = _project_score(node, pose)
        ranked.append(_FrameCandidate(path, score, visible, order))
    visible = [candidate for candidate in ranked if candidate.in_view]
    pool = visible or ranked
    return sorted(pool, key=lambda item: (-item.score, item.order))


def _best_frame_score(
    path: pathlib.Path,
    graph: SceneGraph,
    pose_by_key: dict[str, _PoseEvidence],
) -> tuple[float, bool]:
    pose = pose_by_key.get(_frame_key(path.name))
    if pose is None:
        return -100.0, False
    scores = [_project_score(node, pose) for node in graph.nodes if node.kind == "object"]
    if not scores:
        return 0.0, False
    return max(scores, key=lambda item: item[0])


def _frame_key(value: str) -> str:
    match = _FRAME_NUMBER.search(pathlib.Path(value).name)
    if match:
        return f"frame-{int(match.group(1))}"
    return pathlib.Path(value).stem.casefold()


def _load_poses(poses_path: pathlib.Path | None) -> list[_PoseEvidence]:
    if poses_path is None:
        return []
    try:
        payload = json.loads(pathlib.Path(poses_path).read_bytes())
    except (OSError, TypeError, ValueError, UnicodeDecodeError):
        return []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        possible = payload.get("poses") or payload.get("frames")
        items = possible if isinstance(possible, list) else []
    else:
        items = []
    poses: list[_PoseEvidence] = []
    for order, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("image"), str):
            continue
        transform = _numbers(item.get("transform"), 16)
        intrinsics = _numbers(item.get("intrinsics"), 9)
        if transform is None:
            continue
        poses.append(_PoseEvidence(
            frame_key=_frame_key(item["image"]),
            orientation=str(item.get("orientation") or "").casefold(),
            transform=transform,
            intrinsics=intrinsics or (),
            order=order,
        ))
    return poses


def _numbers(value: object, length: int) -> tuple[float, ...] | None:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        return None
    try:
        numbers = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    return numbers if all(math.isfinite(item) for item in numbers) else None


def _project_score(node: SceneNode, pose: _PoseEvidence) -> tuple[float, bool]:
    matrix = pose.transform
    if len(matrix) != 16 or not all(math.isfinite(value) for value in matrix):
        return -100.0, False
    position = node.transform.position
    # Pose metadata stays in ARKit's Y-up, column-major coordinates.  Convert
    # the measured point back to that frame and use the camera basis directly;
    # conjugating the matrix would rotate the camera's local axes a second
    # time.  ARKit cameras look down local -Z.
    world = (position.x, position.z, -position.y)
    camera = (matrix[12], matrix[13], matrix[14])
    delta = (world[0] - camera[0], world[1] - camera[1], world[2] - camera[2])
    right = (matrix[0], matrix[1], matrix[2])
    up = (matrix[4], matrix[5], matrix[6])
    backward = (matrix[8], matrix[9], matrix[10])
    local_x = sum(delta[index] * right[index] for index in range(3))
    local_y = sum(delta[index] * up[index] for index in range(3))
    local_z = sum(delta[index] * backward[index] for index in range(3))
    depth = -local_z
    distance = math.sqrt(sum(value * value for value in delta))
    if depth <= 0.05 or distance <= 0.05:
        return -distance, False

    fx = pose.intrinsics[0] if len(pose.intrinsics) >= 5 and pose.intrinsics[0] > 0 else 1000.0
    fy = pose.intrinsics[4] if len(pose.intrinsics) >= 5 and pose.intrinsics[4] > 0 else fx
    cx = pose.intrinsics[6] if len(pose.intrinsics) >= 8 and pose.intrinsics[6] > 0 else 960.0
    cy = pose.intrinsics[7] if len(pose.intrinsics) >= 8 and pose.intrinsics[7] > 0 else 720.0
    width, height = max(2.0 * cx, 1.0), max(2.0 * cy, 1.0)
    projected_x = fx * local_x / depth + cx
    projected_y = fy * local_y / depth + cy
    margin_x, margin_y = width * 0.25, height * 0.25
    in_view = (
        -margin_x <= projected_x <= width + margin_x
        and -margin_y <= projected_y <= height + margin_y
    )
    center_offset = abs(projected_x - cx) / (width / 2) + abs(projected_y - cy) / (height / 2)
    alignment = min(1.0, depth / distance)
    score = (10.0 if in_view else -4.0) + alignment * 4.0 - center_offset - distance * 0.02
    return score, in_view


def _image_messages(
    graph: SceneGraph,
    frame_paths: Iterable[pathlib.Path] | None,
    poses_path: pathlib.Path | None,
) -> list[dict[str, Any]]:
    if not frame_paths:
        return []
    paths = select_keyframes(graph, frame_paths, poses_path)
    pose_by_key = {pose.frame_key: pose for pose in _load_poses(poses_path)}
    messages: list[dict[str, Any]] = []
    total_bytes = 0
    for path in paths:
        pose = pose_by_key.get(_frame_key(path.name))
        encoded = _encode_frame(path, pose.orientation if pose else "")
        if encoded is None or total_bytes + len(encoded) > MAX_IMAGE_BYTES:
            continue
        total_bytes += len(encoded)
        messages.append({
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii")},
        })
    return messages


def _encode_frame(path: pathlib.Path, orientation: str) -> bytes | None:
    """Validate and normalize an uploaded frame before embedding its bytes."""
    try:
        source = pathlib.Path(path)
        if source.stat().st_size > MAX_SOURCE_IMAGE_BYTES:
            return None
        raw = source.read_bytes()
    except (OSError, TypeError, ValueError):
        return None
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(raw)) as opened:
            if opened.width * opened.height > MAX_SOURCE_IMAGE_PIXELS:
                return None
            opened.verify()
        with Image.open(io.BytesIO(raw)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
        if orientation.startswith("portrait") and image.width > image.height:
            image = image.transpose(Image.Transpose.ROTATE_270)
        elif orientation.startswith("landscape") and image.height > image.width:
            image = image.transpose(Image.Transpose.ROTATE_90)
        image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
        for quality in IMAGE_JPEG_QUALITIES:
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=quality, optimize=True)
            encoded = output.getvalue()
            if len(encoded) <= MAX_IMAGE_BYTES:
                return encoded
    except (ImportError, OSError, TypeError, ValueError):
        return None
    return None


def _context(graph: SceneGraph, *, images_provided: bool = False) -> dict[str, Any]:
    return {
        "walls": [_surface_brief(node) for node in graph.nodes if node.kind == "wall"],
        "objects": [_object_brief(node) for node in graph.nodes if node.kind == "object"],
        "doors": [_surface_brief(node) for node in graph.nodes if node.kind == "door"],
        "images_provided": images_provided,
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
    deadline = time.monotonic() + REQUEST_TIMEOUT_SECONDS
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("openrouter_request_deadline")
    with urllib.request.urlopen(request, timeout=remaining) as response:
        raw = _read_response(response, deadline)
    if time.monotonic() > deadline:
        raise TimeoutError("openrouter_request_deadline")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("openrouter_not_an_object")
    return parsed


def _read_response(response: Any, deadline: float) -> bytes:
    """Read a response under one deadline, including slow heartbeat chunks."""
    chunks: list[bytes] = []
    total = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("openrouter_response_deadline")
        _set_response_timeout(response, remaining)
        chunk = response.read1(min(64 * 1024, MAX_RESPONSE_BYTES - total + 1))
        if not chunk:
            break
        if not isinstance(chunk, (bytes, bytearray)):
            raise ValueError("openrouter_response_not_bytes")
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise ValueError("openrouter_response_too_large")
        chunks.append(bytes(chunk))
    return b"".join(chunks)


def _set_response_timeout(response: Any, seconds: float) -> None:
    stream = getattr(response, "fp", None)
    raw = getattr(stream, "raw", None)
    socket = getattr(raw, "_sock", None) or getattr(stream, "_sock", None)
    setter = getattr(socket, "settimeout", None)
    if callable(setter):
        setter(max(0.001, seconds))


def _patches_from_model(
    payload: dict, graph: SceneGraph, *, allow_appearance: bool = True
) -> list[LabelPatch] | None:
    content = _message_content(payload)
    if content is None:
        return None
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or set(parsed) != {"nodes"}:
        return None
    items = parsed.get("nodes")
    if not isinstance(items, list):
        return None
    expected = {node.id for node in graph.nodes if node.kind == "object"}
    if not expected:
        return None
    patches = [_patch_from_item(item, expected, allow_appearance=allow_appearance) for item in items]
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


def _patch_from_item(
    item: object, expected: set[UUID], *, allow_appearance: bool = True
) -> LabelPatch | None:
    if not isinstance(item, dict):
        return None
    if set(item) - {"id", "label", "movable", "quality", "appearance"}:
        return None
    try:
        node_id = UUID(str(item.get("id")))
    except (ValueError, TypeError):
        return None
    label, quality, movable = item.get("label"), item.get("quality"), item.get("movable")
    if node_id not in expected or not isinstance(label, str) or not label.strip() or quality not in {"measured", "needs_another_look"} or not isinstance(movable, bool):
        return None
    raw_appearance = item.get("appearance")
    appearance = None
    if raw_appearance is not None:
        if not allow_appearance:
            return None
        try:
            appearance = DisplayAppearance.model_validate(raw_appearance)
        except (TypeError, ValueError):
            return None
    return LabelPatch(node_id, label.strip()[:80], movable, quality, appearance)
