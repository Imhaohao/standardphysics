"""Plain sentences built from the measured change, so the words and the geometry always agree."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def length(metres: float) -> str:
    """Centimetres to the nearest 5 below a metre, tenths of a metre above, rounding halves up both ways."""
    centimetres = int(np.floor(metres * 100 / 5 + 0.5)) * 5
    if centimetres < 100:
        return f"{centimetres} cm"
    return f"{np.floor(metres * 10 + 0.5) / 10:.1f} m"


def size_phrase(size: np.ndarray) -> str:
    width, depth, height = (length(float(v)) for v in (max(size[0], size[1]), min(size[0], size[1]), size[2]))
    return f"about {width} by {depth} and {height} tall"


def article(phrase: str) -> str:
    return "an" if phrase[:1].lower() in "aeiou" else "a"


QUALIFIERS = frozenset({"with", "of", "in", "on", "from", "for", "near", "under", "and"})


def head_noun(phrase: str) -> str:
    """The word the phrase is about: "seat" in "wooden seat with black metal legs"."""
    words = phrase.lower().split()
    cut = next((index for index, word in enumerate(words) if word in QUALIFIERS and index > 0), len(words))
    return words[cut - 1] if words else ""


def is_plural(phrase: str) -> bool:
    head = head_noun(phrase)
    return head.endswith("s") and not head.endswith(("ss", "us", "is"))


def some(phrase: str) -> str:
    """ "a box", "an armchair", or "plates" with no article for more than one."""
    return phrase if is_plural(phrase) else f"{article(phrase)} {phrase}"


def turn_phrase(turn_deg: float | None) -> str:
    if turn_deg is None or abs(turn_deg) < 20:
        return ""
    rounded = int(round(abs(turn_deg) / 15) * 15)
    if rounded >= 180:
        return " and turned around"
    side = "counterclockwise" if turn_deg > 0 else "clockwise"
    return f" and turned about {rounded}° {side}"


def plain_noun(size_m) -> str:
    """What to call a thing when the views can't agree what it is: an object, sized by its box."""
    longest = float(max(size_m))
    if longest < 0.35:
        return "small object"
    return "large object" if longest > 1.2 else "object"


def _where(phrase: str) -> str:
    return f" {phrase}" if phrase else ""


@dataclass(frozen=True)
class Route:
    """Where a moved object was and is, in words, plus what it passed or headed for on the way."""

    before: str = ""
    after: str = ""
    crossed: str = ""
    heading: str = ""


def _from(place: str) -> str:
    """ "from on the table" reads as "from the table"."""
    return "from " + (place[3:] if place.startswith("on ") else place)


def _to(place: str) -> str:
    """ "to on the open floor" reads as "onto the open floor"."""
    return "onto " + place[3:] if place.startswith("on ") else "to " + place


def route_phrase(route: Route) -> str:
    if route.crossed and route.before:
        return f" {_from(route.before)} to the other side of the {route.crossed}"
    if route.before and route.after and route.before != route.after:
        return f" {_from(route.before)} {_to(route.after)}"
    if route.heading:
        return f" toward the {route.heading}"
    return f" to a spot {route.after}" if route.after else ""


def moved_sentence(name: str, distance_m: float, turn_deg: float | None, route: Route = Route()) -> str:
    return f"The {name} moved {length(distance_m)}{route_phrase(route)}{turn_phrase(turn_deg)}."


def removed_sentence(detail: str, where: str) -> str:
    return f"The {detail}{_where(where)} is gone."


def added_sentence(detail: str, where: str) -> str:
    return f"{_capital(some(detail))} appeared{_where(where)}."


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def partly_seen(sentence: str) -> str:
    """The same sentence, admitting that the video only ever saw part of the object."""
    return f"{sentence[:-1]}; only part of it was ever in view, so it may be larger."


def unchecked_sentence(detail: str, where: str, video: str) -> str:
    """Seen only after, it may be new; seen only before, it may since have gone."""
    other = "before" if video == "after" else "after"
    doubt = "may or may not be new" if video == "after" else "may or may not still be there"
    shows, it = ("show", "they") if is_plural(detail) else ("shows", "it")
    return (f"{_capital(some(detail))}{_where(where)} {shows} only in the {video} video; "
            f"the {other} video never looked there, so {it} {doubt}.")


def unsupported_sentence(detail: str, kind: str, bottom_m: float) -> str:
    """A box with nothing under it: worth showing, not worth counting."""
    verb = ("seem" if is_plural(detail) else "seems") + (" to have appeared" if kind == "added" else " to have gone")
    return (f"{_capital(some(detail))} {verb} {length(bottom_m)} above the floor with nothing under most of it, "
            "so it is more likely a misread surface than a change and is not counted.")


def short_clause(change: dict) -> str:
    name = change["name"]
    if change["type"] == "moved":
        return f"the {name} moved {length(change['distance_m'])}"
    if change["type"] == "added":
        return f"{some(name)} appeared"
    return f"the {name} was removed"


def summary(changes: list[dict]) -> str:
    if not changes:
        return "Nothing in the room moved, appeared or disappeared between the two videos."
    clauses = [short_clause(change) for change in changes]
    listed = clauses[0] if len(clauses) == 1 else ", ".join(clauses[:-1]) + f" and {clauses[-1]}"
    count = "One thing" if len(changes) == 1 else f"{len(changes)} things"
    return f"{count} changed between the videos: {listed}."
