"""Relations coined by a model for the things that touch, each kept only if its own predicate holds.

The model is shown every pair of things that touch or nearly touch, what each
was called, and what the engine measured between them. It names the relations
it sees and writes, for each, the predicate over the substrate that makes it
true. The engine then runs every predicate against the real geometry and keeps
only the relations whose predicate holds: the model supplies structure, the
engine supplies values, and a relation whose justification fails is dropped.

Holding on its own pair is not enough. The first real run had every predicate
true where it was written and one of them true of every pair in the room. So
each predicate is also run over every pair, and when it selects pairs the model
did not name, the model is shown them and must say which the relation really
covers and tighten the predicate to exclude the rest. A relation survives only
when its predicate selects exactly the pairs the model stands behind.

Coining goes to OpenRouter because writing a correct predicate needs a frontier
model: in the experiment recorded in docs/ARCHITECTURE.md, the open-weight
models on Fireworks invented operators and wrote predicates that selected the
floor as precariously balanced.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
from standardphysics_pipeline.interpretation.entities import Entity
from standardphysics_pipeline.interpretation.predicates import MEASUREMENTS
from standardphysics_pipeline.interpretation.relations import Relation, both_ways, facts, kept, neighbours, selected

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
    ordered = both_ways(pairs)
    exact, loose = _judged(_kinds(kept(proposed, entities, down)), ordered, entities, down)
    tightened = [kind for start in range(0, len(loose), KINDS_PER_CALL)
                 for kind in _tightened(loose[start:start + KINDS_PER_CALL], ordered, entities, down, models)]
    return [relation for kind in exact + tightened for relation in kind.relations()]


KINDS_PER_CALL = 12
"""Loose relations sent back in one request."""

SHOWN_EXTRAS = 30
"""Pairs a loose predicate also selects that are shown to the model. A predicate
tightened from fewer than it really selects is still checked against all of them."""


@dataclass(frozen=True)
class _Kind:
    """One coined relation: a name, its predicate, and every ordered pair it is claimed for."""

    name: str
    because: dict
    covers: frozenset

    def relations(self) -> list[Relation]:
        return [Relation(self.name, source, target, self.because) for source, target in sorted(self.covers, key=str)]


def _kinds(relations: list[Relation]) -> list[_Kind]:
    """The relations gathered by name and predicate: one written predicate is one claim about the room."""
    gathered: dict[tuple, list[Relation]] = {}
    for relation in relations:
        gathered.setdefault((relation.name.lower(), json.dumps(relation.because, sort_keys=True)), []).append(relation)
    return [
        _Kind(group[0].name, group[0].because, frozenset((r.source, r.target) for r in group))
        for group in gathered.values()
    ]


def _judged(kinds: list[_Kind], ordered, entities, down) -> tuple[list[_Kind], list[tuple[_Kind, list]]]:
    """Kinds whose predicate selects only what they claim, and the rest with what else they select."""
    exact, loose = [], []
    by_id = {entity.id: entity for entity in entities}
    for kind in kinds:
        extra = selected(kind.because, ordered, entities, down) - kind.covers
        if extra:
            loose.append((kind, sorted(((by_id[s], by_id[t]) for s, t in extra), key=lambda pair: str(pair[0].id))))
        else:
            exact.append(kind)
    return exact, loose


TIGHTEN_INSTRUCTION = INSTRUCTION + """

This is a second pass. Each relation below was coined for some pairs, and its
predicate was run over every pair of touching things in the room. It is also true of
the pairs listed under `also_selected`, which it was not coined for. For each relation,
say which of those the relation truly describes (`also_applies`, by index), and write a
tightened predicate that is true of the pairs it was coined for and of `also_applies`,
and false of every other pair in the room. A relation you cannot tighten that way,
leave out."""

TIGHTEN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["relations"],
    "properties": {
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["relation", "also_applies", "because"],
                "properties": {
                    "relation": {"type": "integer"},
                    "also_applies": {"type": "array", "items": {"type": "integer"}},
                    "because": {"type": "string"},
                },
            },
        },
    },
}


def _tightened(batch: list[tuple[_Kind, list]], ordered, entities, down, models: OpenRouter) -> list[_Kind]:
    by_id = {entity.id: entity for entity in entities}
    shown = [_shown_kind(index, kind, extra, by_id, down) for index, (kind, extra) in enumerate(batch)]
    answer = models.structured(
        TIGHTEN_INSTRUCTION, {"relations": shown}, TIGHTEN_SCHEMA, "tightened", max_tokens=MAX_ANSWER_TOKENS
    )
    if isinstance(answer, Rejected):
        return []
    return [kind for item in answer.payload.get("relations", [])
            if (kind := _accepted(item, batch, ordered, entities, down))]


def _shown_kind(index: int, kind: _Kind, extra: list, by_id: dict, down: np.ndarray) -> dict:
    def pair(source, target):
        return {"from": source.name, "to": target.name, "measured": facts(source, target, down)}

    return {
        "relation": index,
        "name": kind.name,
        "because": json.dumps(kind.because),
        "coined_for": [pair(by_id[s], by_id[t]) for s, t in sorted(kind.covers, key=str)],
        "also_selected": [dict(pair(s, t), index=n) for n, (s, t) in enumerate(extra[:SHOWN_EXTRAS])],
    }


def _accepted(item: dict, batch: list[tuple[_Kind, list]], ordered, entities, down) -> _Kind | None:
    """The tightened relation, when its predicate selects exactly what it was coined for plus what the model added."""
    index = item.get("relation")
    if not isinstance(index, int) or not 0 <= index < len(batch):
        return None
    kind, extra = batch[index]
    added = {n for n in item.get("also_applies", []) if isinstance(n, int) and 0 <= n < min(len(extra), SHOWN_EXTRAS)}
    try:
        because = json.loads(item.get("because", ""))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(because, dict):
        return None
    wanted = kind.covers | {(extra[n][0].id, extra[n][1].id) for n in added}
    if selected(because, ordered, entities, down) != wanted:
        return None
    return _Kind(kind.name, because, frozenset(wanted))


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
