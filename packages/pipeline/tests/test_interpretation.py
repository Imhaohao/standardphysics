"""Things and relations coined over a real scan, and the predicates that keep relations honest.

The scan is a real phone capture. Predicates are written here because they are
what is under test; the geometry they are run against is never made up.
"""

from __future__ import annotations

import json
import pathlib
import uuid
from collections import Counter

import numpy as np
import pytest
from standardphysics_pipeline.ingest import parse_room_json
from standardphysics_pipeline.interpretation.entities import coin_entities
from standardphysics_pipeline.interpretation.predicates import PredicateError, Scope, holds
from standardphysics_pipeline.interpretation.relations import Relation, kept, neighbours
from standardphysics_pipeline.substrate import gravity, volume
from standardphysics_pipeline.substrate.segment import pieces_of

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCAN = ROOT / "datasets/phone/test1"

RESTS_ON = {
    "all": [
        {"op": "gap", "a": "$from", "b": "$to", "along": "up", "under": 0.05, "over": -0.05},
        {"op": "footprint_overlap", "a": "$from", "b": "$to", "along": "up", "over": 0.5},
    ]
}
"""Underside within five centimetres of the other's top, and mostly over it."""


@pytest.fixture(scope="module")
def room():
    if not (SCAN / "lidar-mesh.json").is_file():
        pytest.skip("no scanned room with a mesh on this machine")
    graph = parse_room_json(json.loads((SCAN / "room.json").read_text()))
    pieces = pieces_of(SCAN / "lidar-mesh.json", graph.capture_to_room)
    return graph, pieces, coin_entities(pieces, graph), gravity(graph)


def _lowest(entities, down):
    """The thing whose top is lowest: what everything stands on, found without its name."""
    return min(entities, key=lambda entity: float(np.max(_corners_along(entity.region, -down))))


def _corners_along(region, direction):
    from standardphysics_pipeline.substrate import corners

    return corners(region) @ direction


def _scope(entities, down, source, target):
    return Scope({str(e.id): e.region for e in entities}, down, {"$from": str(source.id), "$to": str(target.id)})


class TestThings:
    def test_every_measured_thing_is_a_thing_under_its_own_id(self, room):
        graph, _pieces, entities, _down = room
        assert [entity.id for entity in entities] == [node.id for node in graph.nodes]

    def test_no_piece_belongs_to_two_things(self, room):
        _graph, _pieces, entities, _down = room
        owned = Counter(piece for entity in entities for piece in entity.pieces)
        assert owned and max(owned.values()) == 1

    def test_most_solid_things_wear_measured_surface(self, room):
        _graph, _pieces, entities, _down = room
        solid = [entity for entity in entities if volume(entity.region) > 0]
        assert sum(bool(entity.pieces) for entity in solid) >= 0.8 * len(solid)


class TestPredicates:
    def test_what_stands_on_the_lowest_thing_rests_on_it_and_not_the_other_way(self, room):
        _graph, _pieces, entities, down = room
        floor = _lowest(entities, down)
        standing = [e for e in entities if e.id != floor.id and volume(e.region) > 0.05]
        resting = [e for e in standing if holds(RESTS_ON, _scope(entities, down, e, floor))]
        assert len(resting) >= 0.75 * len(standing)
        assert not any(holds(RESTS_ON, _scope(entities, down, floor, e)) for e in resting)

    def test_not_turns_a_predicate_round(self, room):
        _graph, _pieces, entities, down = room
        floor = _lowest(entities, down)
        thing = next(e for e in entities if e.id != floor.id and volume(e.region) > 0.05)
        scope = _scope(entities, down, thing, floor)
        assert holds({"not": RESTS_ON}, scope) is not holds(RESTS_ON, scope)

    @pytest.mark.parametrize("written", [
        {"op": "teleports", "a": "$from", "b": "$to", "under": 1},
        {"op": "gap", "a": "$from", "b": "$to", "under": 1},
        {"op": "gap", "a": "$from", "b": "$to", "along": "sideways", "under": 1},
        {"op": "gap", "a": "$from", "b": "$to", "along": "up"},
        {"op": "volume", "a": "$from", "under": 1, "label": "chair"},
        {"all": []},
        {"all": [RESTS_ON], "any": [RESTS_ON]},
        "rests on",
    ])
    def test_a_predicate_outside_the_language_is_refused(self, room, written):
        _graph, _pieces, entities, down = room
        with pytest.raises(PredicateError):
            holds(written, _scope(entities, down, entities[0], entities[1]))


class TestRelations:
    def test_only_relations_whose_predicate_holds_are_kept(self, room):
        _graph, _pieces, entities, down = room
        floor = _lowest(entities, down)
        thing = next(e for e in entities if e.id != floor.id and holds(RESTS_ON, _scope(entities, down, e, floor)))
        claimed = [
            Relation("rests on", thing.id, floor.id, RESTS_ON),
            Relation("rests on", thing.id, floor.id, RESTS_ON),
            Relation("holds up", floor.id, thing.id, RESTS_ON),
            Relation("rests on", thing.id, floor.id, {"op": "levitates"}),
            Relation("rests on", thing.id, uuid.uuid4(), RESTS_ON),
            Relation("rests on", thing.id, thing.id, RESTS_ON),
        ]
        assert kept(claimed, entities, down) == [claimed[0]]

    def test_a_relation_does_not_depend_on_what_things_are_called(self, room):
        """Every name scrambled to nonsense; every predicate judges the same."""
        _graph, _pieces, entities, down = room
        floor = _lowest(entities, down)
        claimed = [Relation("rests on", e.id, floor.id, RESTS_ON) for e in entities if e.id != floor.id]
        scrambled = [type(e)(e.id, f"zq{index}", e.pieces, e.region) for index, e in enumerate(entities)]
        assert kept(claimed, entities, down) == kept(claimed, scrambled, down)

    def test_things_that_touch_are_offered_as_pairs(self, room):
        _graph, _pieces, entities, down = room
        floor = _lowest(entities, down)
        paired = {frozenset((a.id, b.id)) for a, b in neighbours(entities)}
        resting = [e for e in entities if e.id != floor.id and holds(RESTS_ON, _scope(entities, down, e, floor))]
        assert resting and all(frozenset((e.id, floor.id)) in paired for e in resting)
