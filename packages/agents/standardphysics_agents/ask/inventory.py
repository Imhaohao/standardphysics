"""How many of something there is.

The plainest question in the app, and the one that proves the model of the room
is really a model of the room. Counting is also the thing a rearrangement must
never change, so the same numbers appear on a before and after.
"""

from __future__ import annotations

from standardphysics_contracts import SceneNode

from ..numbers import COUNT_WORDS, plural
from ..tracing import traced
from . import subjects
from .answer import Answer, AskContext
from .locus import subject_locus
from .query import Query

COUNTABLE_KINDS = frozenset({"object", "door", "window", "opening"})

FURNITURE = frozenset({"object"})
"""What to list back when the shop has none of whatever was asked about.

Doors count when somebody asks about doors, and they are not an answer to
"how many sofas do I have".
"""


def _counts(nodes: list[SceneNode]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for node in nodes:
        tally[node.label] = tally.get(node.label, 0) + 1
    return tally


def _number(count: int) -> str:
    return COUNT_WORDS.get(count, str(count))


def _phrase(label: str, count: int) -> str:
    if count == 1:
        return f"one {label.casefold()}"
    return f"{_number(count)} {plural(label)}"


def _listed(tally: dict[str, int]) -> str:
    parts = [_phrase(label, count) for label, count in sorted(tally.items())]
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"


def everything_countable(context: AskContext) -> list[SceneNode]:
    return [n for n in context.graph.nodes if n.kind in COUNTABLE_KINDS]


def furniture(context: AskContext) -> list[SceneNode]:
    return [n for n in context.graph.nodes if n.kind in FURNITURE]


@traced("ask.count")
def count(query: Query, context: AskContext) -> Answer:
    found = subjects.resolve(
        context.graph, query.subject_node_ids, query.subject_labels
    )
    countable = [node for node in found if node.kind in COUNTABLE_KINDS]
    if not countable:
        return _nothing_like_that(query, context)

    tally = _counts(countable)
    asked = query.subject_labels[0] if query.subject_labels else "them"
    return Answer(
        text=f"You have {_listed(tally)}.",
        kind="COUNT",
        query=query,
        subjects=tuple(node.id for node in countable),
        locus=subject_locus(countable, _listed(tally)),
        data={"counts": tally, "total": len(countable), "asked_about": asked},
    )


def _nothing_like_that(query: Query, context: AskContext) -> Answer:
    """A count of nothing is still an answer, so it comes with what is there."""
    asked = query.subject_labels[0].casefold() if query.subject_labels else "that"
    tally = _counts(furniture(context))
    return Answer(
        text=f"You have no {plural(asked)}. You have {_listed(tally)}.",
        kind="COUNT",
        query=query,
        data={"counts": {}, "total": 0, "asked_about": asked, "instead": tally},
    )
