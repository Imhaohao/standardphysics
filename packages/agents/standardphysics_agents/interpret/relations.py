"""Relations coined by a model for the things that touch, each kept only if its own predicate holds.

The model is shown every pair of things that touch or nearly touch, what each
was called, and what the engine measured between them. It names the relations
it sees and writes, for each, the predicate over the substrate that makes it
true. The engine then runs every predicate against the real geometry and keeps
only the relations whose predicate holds: the model supplies structure, the
engine supplies values, and a relation whose justification fails is dropped.

Coining goes to OpenRouter because writing a correct predicate needs a frontier
model: in the experiment recorded in docs/ARCHITECTURE.md, the open-weight
models on Fireworks invented operators and wrote predicates that selected the
floor as precariously balanced.
"""

from __future__ import annotations

import json

import numpy as np
from standardphysics_pipeline.interpretation.entities import Entity
from standardphysics_pipeline.interpretation.predicates import MEASUREMENTS
from standardphysics_pipeline.interpretation.relations import Relation, facts, kept, neighbours

from ..models import OpenRouter
from ..router.decision import Rejected

PAIRS_PER_CALL = 40
"""Pairs sent in one request: a room's worth, with room to answer in under a few thousand tokens."""

MAX_ANSWER_TOKENS = 8000

INSTRUCTION = f"""A room was scanned. Below are pairs of things in it that touch or nearly
touch: what each was called, and what was measured between them, in metres. "up" is
the direction opposite to gravity, as the phone measured it.

Name the relations you see between the two things of each pair, in a few plain words
of your own (for example how one holds, carries, encloses or leans against the
other). A pair may have none, one or several.

For each relation, write `because`: a predicate, as a JSON string, that is true of
the two things exactly when the relation holds. Refer to the thing the relation
starts from as "$from" and the other as "$to". The predicate language:

  {{"all": [p, ...]}}  {{"any": [p, ...]}}  {{"not": p}}
  {{"op": <measurement>, ...arguments, "under": number and/or "over": number}}

Measurements, with their arguments:
{json.dumps({name: sorted(needs) for name, (needs, _) in MEASUREMENTS.items()})}
  gap(a, b, along): how far a begins beyond where b ends along `along`. With along
    "up", it is how far a's underside sits above b's top; negative means they overlap.
  overlap_fraction(a, b): share of a's volume inside b.
  footprint_overlap(a, b, along): share of a's outline, seen along `along`, inside b's.
  contact_area(a, b): square metres of a's surface lying against b's.
  separation(a, b): metres between the two, negative when they interpenetrate.
  rise(a, b, along): how far a's middle is beyond b's middle along `along`.
  extent(a, along): a's length along `along`.  volume(a): cubic metres.
`along` is "up", "down" or three numbers.

The engine runs every predicate on the real geometry and drops any relation whose
predicate is false or malformed, so write predicates that are true for this pair and
would be false for things that do not stand in that relation. Never put a measured
number into a name."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["relations"],
    "properties": {
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["pair", "starts_at", "name", "because"],
                "properties": {
                    "pair": {"type": "integer"},
                    "starts_at": {"type": "string", "enum": ["first", "second"]},
                    "name": {"type": "string"},
                    "because": {"type": "string"},
                },
            },
        },
    },
}


def coin_relations(entities: list[Entity], down: np.ndarray, models: OpenRouter | None = None) -> list[Relation]:
    """Every relation a model coined between touching things whose predicate holds on the measured geometry."""
    models = models or OpenRouter()
    if not models.configured:
        return []
    pairs = neighbours(entities)
    proposed: list[Relation] = []
    for start in range(0, len(pairs), PAIRS_PER_CALL):
        proposed += _proposed(pairs[start:start + PAIRS_PER_CALL], down, models)
    return kept(proposed, entities, down)


def _proposed(pairs: list[tuple[Entity, Entity]], down: np.ndarray, models: OpenRouter) -> list[Relation]:
    shown = [
        {"pair": index, "first": first.name, "second": second.name, "measured": facts(first, second, down)}
        for index, (first, second) in enumerate(pairs)
    ]
    answer = models.structured(INSTRUCTION, {"pairs": shown}, SCHEMA, "relations", max_tokens=MAX_ANSWER_TOKENS)
    if isinstance(answer, Rejected):
        return []
    return [relation for item in answer.payload.get("relations", []) if (relation := _relation(item, pairs))]


def _relation(item: dict, pairs: list[tuple[Entity, Entity]]) -> Relation | None:
    """The model's answer as a relation, or nothing when it names no pair or its predicate is not JSON."""
    index = item.get("pair")
    if not isinstance(index, int) or not 0 <= index < len(pairs):
        return None
    try:
        because = json.loads(item.get("because", ""))
    except (json.JSONDecodeError, TypeError):
        return None
    first, second = pairs[index]
    source, target = (first, second) if item.get("starts_at") == "first" else (second, first)
    name = str(item.get("name", "")).strip()
    if not name or not isinstance(because, dict):
        return None
    return Relation(name=name, source=source.id, target=target.id, because=because)
