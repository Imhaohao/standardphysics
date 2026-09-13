"""Working out which pieces of furniture a question is about.

"How many chairs do I have" names a kind of thing. "How tall is the counter"
names one. "Where are the tables by the window" names some of them. All three
arrive as a label, and a label has to be matched against what the scan
actually found, which is a different vocabulary: Astra says "Ordering counter"
and the owner says "the counter".
"""

from __future__ import annotations

from uuid import UUID

from standardphysics_contracts import SceneGraph, SceneNode

ROOM_WORDS = frozenset({"room", "shop", "floor", "space", "store", "place"})

STOP_WORDS = frozenset({"the", "a", "an", "my", "our", "some", "all", "every"})


def _words(text: str) -> list[str]:
    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    return [w for w in cleaned.casefold().split() if w not in STOP_WORDS]


def _singular(word: str) -> str:
    """Enough of English to match what somebody typed against what was scanned.

    "shelves" has to find a "Shelf" and "display cases" has to find a "Display
    case", which is as far as this needs to go.
    """
    if word.endswith("ves") and len(word) > 4:
        return word[:-3] + "f"
    for suffix in ("ses", "hes", "xes"):
        if word.endswith(suffix) and len(word) > len(suffix) + 1:
            return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 2:
        return word[:-1]
    return word


def label_matches(label: str, asked: str) -> bool:
    """Whether a scanned label is what somebody meant by `asked`.

    Matched on words rather than on the whole string, so "counter" finds the
    ordering counter and "display case" finds both of them.
    """
    wanted = {_singular(w) for w in _words(asked)}
    if not wanted:
        return False
    have = {_singular(w) for w in _words(label)}
    return bool(wanted & have)


def by_label(graph: SceneGraph, asked: str) -> list[SceneNode]:
    return [node for node in graph.nodes if label_matches(node.label, asked)]


def is_about_the_room(labels: list[str]) -> bool:
    return any(
        _singular(word) in ROOM_WORDS for label in labels for word in _words(label)
    )


def resolve(
    graph: SceneGraph, node_ids: list[UUID], labels: list[str]
) -> list[SceneNode]:
    """Pinned ids first, then anything matching the words they used."""
    found: list[SceneNode] = []
    seen: set[UUID] = set()
    for node_id in node_ids:
        try:
            node = graph.by_id(node_id)
        except KeyError:
            continue
        if node.id not in seen:
            found.append(node)
            seen.add(node.id)
    for label in labels:
        for node in by_label(graph, label):
            if node.id not in seen:
                found.append(node)
                seen.add(node.id)
    return found


def labels_of(nodes: list[SceneNode]) -> list[str]:
    return [node.label for node in nodes]
