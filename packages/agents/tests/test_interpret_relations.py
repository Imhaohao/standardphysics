"""A model's relations are kept only when their predicates hold on the real scan.

The scan is a real phone capture. Only the model's answer is stood in for,
because what is under test is what the engine does with it.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from standardphysics_agents.interpret.relations import coin_relations
from standardphysics_agents.models import OpenRouter
from standardphysics_pipeline.ingest import parse_room_json
from standardphysics_pipeline.interpretation.entities import coin_entities
from standardphysics_pipeline.interpretation.relations import neighbours
from standardphysics_pipeline.substrate import corners, gravity
from standardphysics_pipeline.substrate.segment import pieces_of
from test_ask import FakeModel

SCAN = pathlib.Path(__file__).resolve().parents[3] / "datasets/phone/test1"

RESTS_ON = {
    "all": [
        {"op": "gap", "a": "$from", "b": "$to", "along": "up", "under": 0.05, "over": -0.05},
        {"op": "footprint_overlap", "a": "$from", "b": "$to", "along": "up", "over": 0.5},
    ]
}


@pytest.fixture(scope="module")
def room():
    if not (SCAN / "lidar-mesh.json").is_file():
        pytest.skip("no scanned room with a mesh on this machine")
    graph = parse_room_json(json.loads((SCAN / "room.json").read_text()))
    return coin_entities(pieces_of(SCAN / "lidar-mesh.json", graph.capture_to_room), graph), gravity(graph)


def _a_thing_on_the_lowest(entities, down):
    """A pair from the offered list whose first thing is the lowest one, and the index of that pair."""
    lowest = min(entities, key=lambda e: float((corners(e.region) @ -down).max()))
    for index, (first, second) in enumerate(neighbours(entities)):
        if lowest.id == first.id:
            return index, second, first
    raise AssertionError("nothing touches the lowest thing")


def test_only_the_relations_whose_predicates_hold_survive(room):
    entities, down = room
    index, thing, lowest = _a_thing_on_the_lowest(entities, down)
    answer = {"relations": [
        {"pair": index, "starts_at": "second", "name": "stands on", "because": json.dumps(RESTS_ON)},
        {"pair": index, "starts_at": "first", "name": "stands on", "because": json.dumps(RESTS_ON)},
        {"pair": index, "starts_at": "second", "name": "floats over", "because": "it is just above"},
        {"pair": 10_000, "starts_at": "second", "name": "stands on", "because": json.dumps(RESTS_ON)},
    ]}
    model = FakeModel(json.dumps(answer))

    found = coin_relations(entities, down, OpenRouter(client=model))

    assert [(r.name, r.source, r.target) for r in found] == [("stands on", thing.id, lowest.id)]
    shown = json.loads(model.requests[0]["messages"][1]["content"])["pairs"]
    assert all(set(pair["measured"]) and isinstance(pair["first"], str) for pair in shown)


def test_no_model_means_no_relations_rather_than_made_up_ones(room):
    entities, down = room
    assert coin_relations(entities, down, OpenRouter(api_key="", client=None)) == []
