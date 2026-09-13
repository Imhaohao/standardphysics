"""Astra can annotate measured geometry, but cannot rewrite it."""

import base64
import io
import json
import uuid

import pytest
from PIL import Image
import standardphysics_pipeline.astra as astra
from standardphysics_pipeline.astra import (
    MAX_IMAGE_BYTES,
    MAX_OUTPUT_TOKENS,
    LabelPatch,
    _chat_body,
    _PoseEvidence,
    _project_score,
    apply_patches,
    reconstruct,
    reconstruct_result,
    select_keyframes,
)
from standardphysics_pipeline.ingest import parse_room_json


def column_major(x: float, y: float, z: float) -> list[float]:
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1]


def element(category, confidence="high", dims=(1.0, 2.0, 0.5), at=(0.0, 0.0, 0.0)):
    return {
        "identifier": str(uuid.uuid4()), "dimensions": list(dims),
        "transform": column_major(*at), "category": category, "confidence": confidence,
    }


def shop_payload():
    return {
        "floors": [element("floor", dims=(8.0, 0.02, 6.0))],
        "walls": [element("wall", dims=(8.0, 2.4, 0.15), at=(0.0, 1.2, -3.0))],
        "doors": [element("door", dims=(1.0, 2.1, 0.08), at=(-3.0, 1.05, 0.0))],
        "objects": [
            element("storage", dims=(3.2, 1.1, 0.7), at=(0.0, 0.55, -2.65)),
            element("chair", dims=(0.5, 0.9, 0.5), at=(1.5, 0.45, 1.0)),
            element("storage", dims=(1.2, 0.9, 0.5), at=(-2.0, 0.45, 1.2)),
        ],
    }


def model_response(*patches):
    return {"choices": [{"message": {"content": '{"nodes":[' + ",".join(patches) + "]}"}}]}


def patch_for(node, label="Display case", movable=True, quality="measured", appearance=None):
    raw = '{"id":"%s","label":"%s","movable":%s,"quality":"%s"' % (
        node.id, label, str(movable).lower(), quality,
    )
    if appearance is not None:
        raw += ',"appearance":' + json.dumps(appearance, separators=(",", ":"))
    return raw + "}"


def test_local_rebuild_keeps_roomplan_provenance_and_measured_identity():
    graph = parse_room_json(shop_payload())
    before = {node.id: (node.dimensions, node.transform) for node in graph.nodes}

    rebuilt = reconstruct(graph)

    counter = next(node for node in rebuilt.nodes if node.label == "Ordering counter")
    assert counter.labeled_by == "roomplan"
    assert not counter.movable
    assert {node.id: (node.dimensions, node.transform) for node in rebuilt.nodes} == before
    assert reconstruct_result(graph).source == "roomplan"


def test_complete_model_response_marks_only_model_labeled_objects_as_astra():
    graph = parse_room_json({"objects": [element("storage"), element("chair")]})
    objects = [node for node in graph.nodes if node.kind == "object"]

    result = reconstruct_result(graph, transport=lambda *_: model_response(
        patch_for(objects[0], "Display case"), patch_for(objects[1], "Chair"),
    ))

    assert result.used_model
    assert [node.labeled_by for node in result.graph.nodes] == ["astra", "astra"]


def test_partial_or_malformed_model_response_falls_back_without_partial_mutation():
    graph = parse_room_json(shop_payload())
    objects = [node for node in graph.nodes if node.kind == "object"]

    partial = reconstruct_result(graph, transport=lambda *_: model_response(patch_for(objects[0], "Wrong partial label")))
    malformed = reconstruct_result(graph, transport=lambda *_: {"choices": [{"message": {"content": "not json"}}]})

    assert partial.source == "roomplan"
    assert all(node.label != "Wrong partial label" for node in partial.graph.nodes)
    assert malformed.source == "roomplan"
    assert any(node.label == "Ordering counter" for node in malformed.graph.nodes)


def test_fixed_owner_locked_and_confirmed_nodes_stay_locked_and_confirmed():
    graph = parse_room_json({"objects": [element("refrigerator"), element("chair")]})
    fridge, chair = graph.nodes
    owner_locked = chair.model_copy(update={"labeled_by": "owner", "movable": False, "quality": "confirmed"})
    graph = graph.model_copy(update={"nodes": [fridge, owner_locked]})

    rebuilt = apply_patches(graph, [
        LabelPatch(fridge.id, "Fridge", True, "measured"),
        LabelPatch(owner_locked.id, "Chair", True, "needs_another_look"),
    ], source="astra")

    assert not rebuilt.by_id(fridge.id).movable
    assert not rebuilt.by_id(owner_locked.id).movable
    assert rebuilt.by_id(owner_locked.id).quality == "confirmed"
    assert rebuilt.by_id(owner_locked.id).labeled_by == "owner"


def test_low_quality_evidence_is_never_promoted_by_a_model_patch():
    graph = parse_room_json({"objects": [element("chair", confidence="low")]})
    chair = graph.nodes[0]

    rebuilt = apply_patches(graph, [LabelPatch(chair.id, "Chair", True, "measured")], source="astra")

    assert rebuilt.by_id(chair.id).quality == "needs_another_look"


def test_valid_display_appearance_is_optional_and_keeps_model_source_truthful(tmp_path):
    graph = parse_room_json({"objects": [element("chair")]})
    chair = graph.nodes[0]
    frame = tmp_path / "frame-0000"
    Image.new("RGB", (100, 80), "red").save(frame, format="JPEG")
    result = reconstruct_result(graph, transport=lambda *_: model_response(patch_for(
        chair,
        appearance={"base_color": "#aabbcc", "material": "wood"},
    )), frame_paths=[frame])

    assert result.source == "astra"
    assert result.graph.nodes[0].appearance.model_dump(mode="json") == {
        "base_color": "#aabbcc", "material": "wood", "source": "astra",
    }


def test_invalid_appearance_rejects_the_complete_remote_response():
    graph = parse_room_json({"objects": [element("chair")]})
    chair = graph.nodes[0]
    result = reconstruct_result(graph, transport=lambda *_: model_response(patch_for(
        chair,
        appearance={"base_color": "not-a-color", "material": "wood"},
    )))

    assert result.source == "roomplan"
    assert result.graph.nodes[0].appearance is None
    assert result.graph.nodes[0].label == "Chair"


def test_appearance_is_not_accepted_without_valid_photo_evidence():
    graph = parse_room_json({"objects": [element("chair")]})
    chair = graph.nodes[0]
    result = reconstruct_result(graph, transport=lambda *_: model_response(patch_for(
        chair,
        appearance={"base_color": "#aabbcc", "material": "wood"},
    )))

    assert result.source == "roomplan"
    assert result.graph.nodes[0].appearance is None


def test_context_tells_astra_when_photo_evidence_is_available(tmp_path):
    graph = parse_room_json({"objects": [element("chair")]})
    frame = tmp_path / "frame-0000"
    Image.new("RGB", (100, 80), "red").save(frame, format="JPEG")

    with_photos = _chat_body(graph, frame_paths=[frame])["messages"][1]["content"]
    without_photos = _chat_body(graph)["messages"][1]["content"]

    assert json.loads(with_photos[0]["text"])["images_provided"] is True
    assert json.loads(without_photos)["images_provided"] is False


def test_label_request_bounds_reasoning_and_completion():
    graph = parse_room_json({"objects": [element("chair")]})

    body = _chat_body(graph)

    assert body["reasoning"] == {"effort": "low"}
    assert body["max_tokens"] == MAX_OUTPUT_TOKENS
    assert MAX_OUTPUT_TOKENS == 8_192


def test_response_reader_stops_after_a_slow_heartbeat(monkeypatch):
    clock = [0.0]

    class HeartbeatResponse:
        def read1(self, _size):
            clock[0] += 0.75
            return b"heartbeat"

    monkeypatch.setattr(astra.time, "monotonic", lambda: clock[0])
    with pytest.raises(TimeoutError, match="response_deadline"):
        astra._read_response(HeartbeatResponse(), deadline=1.0)


def test_response_reader_rejects_a_body_over_the_cap(monkeypatch):
    class OversizedResponse:
        def read1(self, size):
            return b"x" * size

    monkeypatch.setattr(astra, "MAX_RESPONSE_BYTES", 4)
    with pytest.raises(ValueError, match="response_too_large"):
        astra._read_response(OversizedResponse(), deadline=float("inf"))


def test_poses_project_in_the_ar_camera_forward_direction():
    graph = parse_room_json({
        "objects": [
            element("chair", at=(0.0, 0.0, -2.0)),
            element("table", at=(0.0, 0.0, 2.0)),
        ],
    })
    pose = _PoseEvidence(
        frame_key="frame-0", orientation="portrait",
        transform=tuple(column_major(0.0, 0.0, 0.0)),
        intrinsics=(100, 0, 50, 0, 100, 50, 50, 50, 1), order=0,
    )

    assert _project_score(graph.nodes[0], pose)[1]
    assert not _project_score(graph.nodes[1], pose)[1]


def test_frame_evidence_is_projected_bounded_normalized_and_embedded(tmp_path):
    graph = parse_room_json({"objects": [element("chair", at=(0.0, 0.0, -2.0))]})
    frame_paths = []
    poses = []
    for index in range(8):
        path = tmp_path / f"frame-{index:04d}"
        image = Image.new("RGB", (1600, 900), (index * 10, 40, 80))
        image.save(path, format="JPEG")
        frame_paths.append(path)
        poses.append({
            "image": f"frames/frame_{index:04d}.jpg",
            "orientation": "portrait",
            "intrinsics": [900, 0, 800, 0, 900, 450, 800, 450, 1],
            "transform": column_major(0.0, 0.0, 0.0),
        })
    poses_path = tmp_path / "poses.json"
    poses_path.write_text(json.dumps(poses))

    selected = select_keyframes(graph, frame_paths, poses_path)
    body = _chat_body(graph, frame_paths=frame_paths, poses_path=poses_path)
    content = body["messages"][1]["content"]

    assert len(selected) <= 6
    assert isinstance(content, list)
    images = content[1:]
    assert 1 <= len(images) <= 6
    encoded = [base64.b64decode(item["image_url"]["url"].split(",", 1)[1]) for item in images]
    assert sum(len(item) for item in encoded) <= MAX_IMAGE_BYTES
    assert all(Image.open(io.BytesIO(item)).height > Image.open(io.BytesIO(item)).width for item in encoded)
    assert all(max(Image.open(io.BytesIO(item)).size) <= 1024 for item in encoded)


def test_invalid_frame_bytes_are_skipped_without_breaking_label_request(tmp_path):
    graph = parse_room_json({"objects": [element("chair")]})
    invalid = tmp_path / "frame-0000"
    invalid.write_bytes(b"not an image")
    valid = tmp_path / "frame-0001"
    Image.new("RGB", (100, 80), "red").save(valid, format="JPEG")

    body = _chat_body(graph, frame_paths=[invalid, valid])
    content = body["messages"][1]["content"]
    assert isinstance(content, list)
    assert len(content) == 2
