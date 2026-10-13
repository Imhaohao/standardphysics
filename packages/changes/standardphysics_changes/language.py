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


def turn_phrase(turn_deg: float | None) -> str:
    if turn_deg is None or abs(turn_deg) < 20:
        return ""
    rounded = int(round(abs(turn_deg) / 15) * 15)
    side = "counterclockwise" if turn_deg > 0 else "clockwise"
    return f" and turned about {rounded}° {side}"


def _where(phrase: str) -> str:
    return f" {phrase}" if phrase else ""


@dataclass(frozen=True)
class Route:
    """Where a moved object was and is, in words, plus what it passed or headed for on the way."""

    before: str = ""
    after: str = ""
    crossed: str = ""
    heading: str = ""


def route_phrase(route: Route) -> str:
    if route.crossed and route.before:
        return f" from {route.before} to the other side of the {route.crossed}"
    if route.before and route.after and route.before != route.after:
        return f" from {route.before} to {route.after}"
    if route.heading:
        return f" toward the {route.heading}"
    return f" to a spot {route.after}" if route.after else ""


def moved_sentence(name: str, distance_m: float, turn_deg: float | None, route: Route = Route()) -> str:
    return f"The {name} moved {length(distance_m)}{route_phrase(route)}{turn_phrase(turn_deg)}."


def removed_sentence(detail: str, where: str) -> str:
    return f"The {detail}{_where(where)} is gone."


def added_sentence(detail: str, where: str) -> str:
    return f"{article(detail).capitalize()} {detail} appeared{_where(where)}."


def partly_seen(sentence: str) -> str:
    """The same sentence, admitting that the video only ever saw part of the object."""
    return f"{sentence[:-1]}; only part of it was ever in view, so it may be larger."


def unchecked_sentence(detail: str, where: str, video: str) -> str:
    other = "before" if video == "after" else "after"
    return (f"{article(detail).capitalize()} {detail}{_where(where)} shows only in the {video} video; "
            f"the {other} video never looked there, so it may or may not be new.")


def short_clause(change: dict) -> str:
    name = change["name"]
    if change["type"] == "moved":
        return f"the {name} moved {length(change['distance_m'])}"
    if change["type"] == "added":
        return f"{article(name)} {name} appeared"
    return f"the {name} was removed"


def summary(changes: list[dict]) -> str:
    if not changes:
        return "Nothing in the room moved, appeared or disappeared between the two videos."
    clauses = [short_clause(change) for change in changes]
    listed = clauses[0] if len(clauses) == 1 else ", ".join(clauses[:-1]) + f" and {clauses[-1]}"
    count = "One thing" if len(changes) == 1 else f"{len(changes)} things"
    return f"{count} changed between the videos: {listed}."
