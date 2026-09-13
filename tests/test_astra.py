"""Astra can annotate measured geometry, but cannot rewrite it."""

import uuid

from standardphysics_pipeline.astra import LabelPatch, apply_patches, reconstruct, reconstruct_result
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


def patch_for(node, label="Display case", movable=True, quality="measured"):
    return '{"id":"%s","label":"%s","movable":%s,"quality":"%s"}' % (
        node.id, label, str(movable).lower(), quality,
    )


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
