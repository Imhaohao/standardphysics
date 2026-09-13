"""How far it is from one thing to another.

Reported as the clear gap between the two pieces, which is what a tape measure
across the floor gives you, rather than centre to centre. Nobody asks how far
apart the middles of their tables are.
"""

from __future__ import annotations

from standardphysics_contracts import SceneNode
from standardphysics_pipeline import gap_between_nodes

from ..numbers import span, things
from ..tracing import traced
from . import subjects
from .answer import Answer, AskContext
from .locus import subject_locus
from .query import Query


def _nearest_pair(
    here: list[SceneNode], there: list[SceneNode]
) -> tuple[SceneNode, SceneNode, float]:
    best: tuple[SceneNode, SceneNode, float] | None = None
    for first in here:
        for second in there:
            if first.id == second.id:
                continue
            gap = gap_between_nodes(first, second)
            if best is None or gap < best[2]:
                best = (first, second, gap)
    return best or (here[0], there[0], 0.0)


@traced("ask.distance")
def distance(query: Query, context: AskContext) -> Answer:
    here = subjects.resolve(
        context.graph, query.subject_node_ids, query.subject_labels
    )
    there = subjects.resolve(context.graph, [], query.other_labels)
    if not here or not there:
        return _one_end_missing(query, bool(here), bool(there))

    first, second, gap = _nearest_pair(here, there)
    from standardphysics_contracts import to_inches

    apart = to_inches(gap)
    text = (
        f"{_name(first)} and {_name(second).casefold()} are {span(apart)} apart "
        "at the closest point."
    )
    return Answer(
        text=text,
        kind="DISTANCE",
        query=query,
        subjects=(first.id, second.id),
        locus=subject_locus([first, second], span(apart)),
        data={"inches": round(apart, 2), "between": [str(first.id), str(second.id)]},
    )


def _name(node: SceneNode) -> str:
    named = things([node.label]) or "it"
    return named[:1].upper() + named[1:]


def _one_end_missing(query: Query, found_here: bool, found_there: bool) -> Answer:
    missing = query.other_labels if found_here else query.subject_labels
    asked = missing[0].casefold() if missing else "one of them"
    return Answer(
        text=f"The scan has no {asked} in it. Point at both pieces in the plan "
        "and we will measure between them.",
        kind="DISTANCE",
        query=query,
        data={"asked_about": asked},
    )
