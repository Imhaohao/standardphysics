"""A model's relations are kept only when their predicates select exactly what the model stands behind.

The scan is a real phone capture. Only the model's answers are stood in for,
because what is under test is what the engine does with them.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from standardphysics_agents.interpret.relations import SHOWN_EXTRAS, coin_relations
from standardphysics_agents.models import OpenRouter
from standardphysics_pipeline.ingest import parse_room_json
from standardphysics_pipeline.interpretation.entities import coin_entities
from standardphysics_pipeline.interpretation.relations import both_ways, neighbours, selected
from standardphysics_pipeline.substrate import corners, gravity, volume
from standardphysics_pipeline.substrate.segment import pieces_of
from test_ask import FakeModel

SCAN = pathlib.Path(__file__).resolve().parents[3] / "datasets/phone/test1"

RESTS_ON = {
    "all": [
        {"op": "gap", "a": "$from", "b": "$to", "along": "up", "under": 0.05, "over": -0.05},
        {"op": "footprint_overlap", "a": "$from", "b": "$to", "along": "up", "over": 0.5},
    ]
}


class Answers(FakeModel):
    """A stand-in model: the coining answer on the first coining call, nothing on later ones, and the tightening answer."""

    def __init__(self, coined: dict, tightened: dict | None = None) -> None:
        super().__init__(None)
        self.coined, self.tightened = coined, tightened

    def create(self, **kwargs):
        kind = kwargs["response_format"]["json_schema"]["name"]
        if kind == "tightened":
            self.content = json.dumps(self.tightened)
        else:
            self.content = json.dumps(self.coined if not self.asked("relations") else {"relations": []})
        return super().create(**kwargs)

    def asked(self, kind: str) -> list[dict]:
        return [r for r in self.requests if r["response_format"]["json_schema"]["name"] == kind]


@pytest.fixture(scope="module")
def room():
    if not (SCAN / "lidar-mesh.json").is_file():
        pytest.skip("no scanned room with a mesh on this machine")
    graph = parse_room_json(json.loads((SCAN / "room.json").read_text()))
    return coin_entities(pieces_of(SCAN / "lidar-mesh.json", graph.capture_to_room), graph), gravity(graph)


def _a_thing_on_the_lowest(entities, down):
    """The offered pair whose first thing is the lowest one, its index, and the thing standing on it."""
    lowest = min(entities, key=lambda e: float((corners(e.region) @ -down).max()))
    for index, (first, second) in enumerate(neighbours(entities)):
        if lowest.id == first.id and volume(second.region) > 0.05:
            return index, second, lowest
    raise AssertionError("nothing touches the lowest thing")


def _coined(index, predicate, name="stands on"):
    return {"pair": index, "starts_at": "second", "name": name, "because": json.dumps(predicate)}


def test_a_loose_predicate_tightened_honestly_covers_what_the_model_stands_behind(room):
    entities, down = room
    index, thing, lowest = _a_thing_on_the_lowest(entities, down)
    everything = selected(RESTS_ON, both_ways(neighbours(entities)), entities, down)
    assert 1 < len(everything) <= SHOWN_EXTRAS
    model = Answers(
        {"relations": [
            _coined(index, RESTS_ON),
            {"pair": index, "starts_at": "second", "name": "floats over", "because": "it is just above"},
            {"pair": 10_000, "starts_at": "second", "name": "stands on", "because": json.dumps(RESTS_ON)},
        ]},
        {"relations": [{"relation": 0, "also_applies": list(range(SHOWN_EXTRAS)), "because": json.dumps(RESTS_ON)}]},
    )

    found = coin_relations(entities, down, OpenRouter(client=model))

    assert {(r.source, r.target) for r in found} == everything
    assert {r.name for r in found} == {"stands on"} and (thing.id, lowest.id) in everything
    shown = json.loads(model.asked("tightened")[0]["messages"][1]["content"])["relations"][0]
    assert len(shown["also_selected"]) == len(everything) - 1


def test_a_loose_predicate_the_model_cannot_tighten_is_dropped(room):
    entities, down = room
    index, _thing, _lowest = _a_thing_on_the_lowest(entities, down)
    model = Answers(
        {"relations": [_coined(index, RESTS_ON)]},
        {"relations": [{"relation": 0, "also_applies": [], "because": json.dumps(RESTS_ON)}]},
    )
    assert coin_relations(entities, down, OpenRouter(client=model)) == []


def test_a_predicate_that_already_selects_only_its_own_pair_needs_no_second_call(room):
    entities, down = room
    index, thing, lowest = _a_thing_on_the_lowest(entities, down)
    size = volume(thing.region)
    only_this = {"all": [RESTS_ON, {"op": "volume", "a": "$from", "over": size * 0.999, "under": size * 1.001}]}
    model = Answers({"relations": [_coined(index, only_this, "is set on")]})

    found = coin_relations(entities, down, OpenRouter(client=model))

    assert [(r.name, r.source, r.target) for r in found] == [("is set on", thing.id, lowest.id)]
    assert not model.asked("tightened")


def test_no_model_means_no_relations_rather_than_made_up_ones(room):
    entities, down = room
    assert coin_relations(entities, down, OpenRouter(api_key="", client=None)) == []
