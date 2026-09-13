"""Astra rebuilds labels. It does not rebuild sizes."""

import uuid

from standardphysics_pipeline.astra import LabelPatch, apply_patches, local_patches, reconstruct
from standardphysics_pipeline.ingest import parse_room_json


def column_major(x: float, y: float, z: float) -> list[float]:
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1]


def element(category, confidence="high", dims=(1.0, 2.0, 0.5), at=(0.0, 0.0, 0.0)):
    return {
        "identifier": str(uuid.uuid4()),
        "dimensions": list(dims),
        "transform": column_major(*at),
        "category": category,
        "confidence": confidence,
    }


def shop_payload():
    """A long storage box against a wall, the fixture-shaped counter case."""
    return {
        "floors": [element("floor", dims=(8.0, 0.02, 6.0), at=(0.0, 0.0, 0.0))],
        "walls": [element("wall", dims=(8.0, 2.4, 0.15), at=(0.0, 1.2, -3.0))],
        "doors": [element("door", dims=(1.0, 2.1, 0.08), at=(-3.0, 1.05, 0.0))],
        "objects": [
            element("storage", dims=(3.2, 1.1, 0.7), at=(0.0, 0.55, -2.65)),
            element("chair", dims=(0.5, 0.9, 0.5), at=(1.5, 0.45, 1.0)),
            element("table", dims=(0.8, 0.75, 0.8), at=(1.5, 0.375, 1.8)),
            element("storage", dims=(1.2, 0.9, 0.5), at=(-2.0, 0.45, 1.2)),
        ],
    }


def test_long_storage_against_a_wall_is_the_ordering_counter():
    graph = reconstruct(parse_room_json(shop_payload()))
    counter = next(node for node in graph.nodes if node.label == "Ordering counter")
    assert not counter.movable
    assert counter.labeled_by == "astra"
    assert counter.raw_category == "storage"
    assert (counter.dimensions.x, counter.dimensions.y, counter.dimensions.z) == (3.2, 0.7, 1.1)


def test_chairs_and_cases_stay_separate_and_movable():
    graph = reconstruct(parse_room_json(shop_payload()))
    by_label = {node.label: node for node in graph.nodes if node.kind == "object"}
    assert by_label["Chair"].movable
    assert by_label["Table"].movable
    assert by_label["Display case"].movable
    assert by_label["Display case"].raw_category == "storage"


def test_the_only_door_becomes_the_front_door():
    graph = reconstruct(parse_room_json(shop_payload()))
    door = next(node for node in graph.nodes if node.kind == "door")
    assert door.label == "Front door"
    assert not door.movable


def test_a_patch_cannot_resize_or_drop_a_node():
    graph = parse_room_json(shop_payload())
    before = {node.id: node.dimensions for node in graph.nodes}
    fake = LabelPatch(
        node_id=graph.nodes[0].id,
        label="Gone",
        movable=True,
        quality="measured",
    )
    after = apply_patches(graph, [fake])
    assert len(after.nodes) == len(graph.nodes)
    assert {node.id: node.dimensions for node in after.nodes} == before
    assert not after.nodes[0].movable


def test_a_refrigerator_stays_fixed_even_if_astra_says_move_it():
    graph = parse_room_json({"objects": [element("refrigerator", dims=(0.9, 1.8, 0.7))]})
    fridge = graph.nodes[0]
    after = apply_patches(
        graph,
        [LabelPatch(fridge.id, "Fridge", True, "measured")],
    )
    assert not after.nodes[0].movable


def test_openrouter_patches_are_used_when_the_transport_answers():
    graph = parse_room_json({"objects": [element("storage", dims=(1.0, 0.9, 0.5))]})
    node = graph.nodes[0]

    def transport(url, body, headers):
        assert "chat/completions" in url
        assert body["model"] == "openai/gpt-6-astra"
        assert headers["Content-Type"] == "application/json"
        return {
            "choices": [{
                "message": {
                    "content": (
                        '{"nodes":[{"id":"%s","label":"Display case",'
                        '"movable":true,"quality":"measured"}]}' % node.id
                    )
                }
            }]
        }

    rebuilt = reconstruct(graph, transport=transport)
    assert rebuilt.nodes[0].label == "Display case"
    assert rebuilt.nodes[0].labeled_by == "astra"


def test_a_broken_model_answer_falls_back_to_local_labels():
    graph = parse_room_json(shop_payload())

    def transport(url, body, headers):
        return {"choices": [{"message": {"content": "not json"}}]}

    rebuilt = reconstruct(graph, transport=transport)
    assert any(node.label == "Ordering counter" for node in rebuilt.nodes)


def test_local_patches_cover_every_node():
    graph = parse_room_json(shop_payload())
    assert {patch.node_id for patch in local_patches(graph)} == {node.id for node in graph.nodes}
