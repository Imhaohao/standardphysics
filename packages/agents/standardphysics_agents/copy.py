"""Every sentence a shop owner reads about a finding.

One place, so a wording change is one edit. Section 2 of the plan governs all of
it: short sentences, ordinary words, inches, no jargon, and nothing whose job is
to point at an absence. A title names what is wrong, the line under it gives the
measurement and what is needed, and the fix says what to do.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .checks.observation import Observation
from .numbers import by, inches, measured, size, things
from .rules import RuleSpec


@dataclass(frozen=True)
class FindingCopy:
    title: str
    detail: str
    fix: str | None = None


STOP_PHRASES = {
    "counter": "the counter",
    "pickup": "where you pick up drinks",
    "seat": "the seats",
    "exit": "the way out",
    "entrance": "the front door",
}


def stop_phrase(name: str | None) -> str:
    if not name:
        return "the next stop"
    return STOP_PHRASES.get(name.strip().casefold(), f"the {name.strip().casefold()}")


def _route_width(observation: Observation, rule: RuleSpec) -> FindingCopy:
    destination = stop_phrase(observation.facts.get("destination"))
    if observation.reason == "unreachable":
        return _route_blocked(observation, destination)
    needed = inches(rule.threshold)
    shown = measured(observation.measured_inches, rule.threshold)
    if observation.satisfied:
        return FindingCopy(
            title=f"The path to {destination} fits",
            detail=f"It's {shown} at the tightest point. Wheelchairs need {needed}.",
        )
    return FindingCopy(
        title=f"The path to {destination} is too narrow",
        detail=f"It's {shown} at the tightest point. Wheelchairs need {needed}.",
        fix=_widen_fix(observation, rule),
    )


def _route_blocked(observation: Observation, destination: str) -> FindingCopy:
    blockers = things(observation.facts.get("blockers", []))
    subject = f"{blockers} sit" if blockers else "Something sits"
    return FindingCopy(
        title=f"There's no way through to {destination}",
        detail=f"{subject} across the path, wall to wall.",
        fix="Move enough of it aside to leave a gap, and we'll measure again.",
    )


def _widen_fix(observation: Observation, rule: RuleSpec) -> str:
    """A fix only ever asks for something the owner can actually do.

    Placement is adjustable and inventory is not, and a built-in counter is
    neither. Naming a fixed fixture in a fix would send the owner to shove a
    wall.
    """
    deficit = inches(rule.threshold - observation.measured_inches)
    movable = things(observation.facts.get("movable_blockers", []))
    fixed = things(observation.facts.get("fixed_blockers", []))
    if movable and len(observation.facts.get("movable_blockers", [])) >= 2:
        return f"Move {movable} {deficit} apart."
    if movable and fixed:
        return f"Move {movable} {deficit} further from {fixed}."
    if movable:
        return f"Move {movable} {deficit} over."
    if fixed:
        return f"Ask a contractor about opening this gap to {inches(rule.threshold)}."
    return f"Clear a path {inches(rule.threshold)} wide."


def _door_width(observation: Observation, rule: RuleSpec) -> FindingCopy:
    door = observation.facts.get("door", "door").casefold()
    needed = inches(rule.threshold)
    shown = measured(observation.measured_inches, rule.threshold)
    if observation.satisfied:
        return FindingCopy(
            title=f"The {door} is wide enough",
            detail=f"It's {shown} clear. Doorways need {needed}.",
        )
    return FindingCopy(
        title=f"The {door} is too narrow",
        detail=f"It's {shown} clear. Doorways need {needed}.",
        fix=f"Widen the {door} to a {size(rule.threshold)} clear opening.",
    )


def _counter_height(observation: Observation, rule: RuleSpec) -> FindingCopy:
    counter = observation.facts.get("counter", "counter").casefold()
    allowed = inches(rule.threshold)
    length = inches(observation.facts.get("accessible_length_inches", 36.0))
    shown = measured(observation.measured_inches, rule.threshold)
    section = f"Make it {length} long and {allowed} high."
    if observation.satisfied:
        return FindingCopy(
            title=f"The {counter} is a good height to order from",
            detail=f"It's {shown} high. Ordering from a wheelchair needs {allowed} or lower.",
        )
    return FindingCopy(
        title=f"The {counter} is too high to order from",
        detail=f"It's {shown} high. Ordering from a wheelchair needs {allowed} or lower.",
        fix=f"Add a lower section to the {counter}. {section}",
    )


def _counter_approach(observation: Observation, rule: RuleSpec) -> FindingCopy:
    counter = observation.facts.get("counter", "counter").casefold()
    needed = by(
        observation.facts.get("required_wide", rule.threshold),
        observation.facts.get("required_deep", 30.0),
    )
    have = by(
        observation.facts.get("measured_wide", 0.0),
        observation.facts.get("measured_deep", 0.0),
    )
    detail = f"The clear floor beside it is {have}. Pulling up needs {needed}."
    if observation.satisfied:
        return FindingCopy(
            title=f"There's room to pull up to the {counter}", detail=detail
        )
    return FindingCopy(
        title=f"There's not enough room to pull up to the {counter}",
        detail=detail,
        fix=f"Clear a space {needed} beside the {counter}.",
    )


def _passing_space(observation: Observation, rule: RuleSpec) -> FindingCopy:
    needed = inches(rule.threshold)
    if not observation.facts.get("applies", True):
        shown = measured(observation.measured_inches)
        return FindingCopy(
            title="Two people can pass anywhere on the path",
            detail=f"It's {shown} wide at the tightest point, and passing needs {needed}.",
        )
    route = inches(observation.facts.get("route_width", 0.0))
    spot = inches(observation.measured_inches or 0.0)
    if observation.satisfied:
        return FindingCopy(
            title="There's a spot to step aside on the path",
            detail=f"The path narrows to {route}, and the widest spot to wait is {spot}.",
        )
    return FindingCopy(
        title="There's nowhere to pass another customer",
        detail=f"The path narrows to {route}, and the widest spot to wait is {spot}. Passing needs {needed}.",
        fix=f"Clear a {size(rule.threshold)} square somewhere along the path.",
    )


def _turning_space(observation: Observation, rule: RuleSpec) -> FindingCopy:
    stop = stop_phrase(observation.facts.get("stop"))
    needed = inches(rule.threshold)
    shown = measured(observation.measured_inches, rule.threshold)
    if observation.satisfied:
        return FindingCopy(
            title=f"There's room to turn around at {stop}",
            detail=f"The clear floor is {shown} across. Turning a wheelchair needs {needed}.",
        )
    return FindingCopy(
        title=f"There's not enough room to turn around at {stop}",
        detail=f"The clear floor is {shown} across. Turning a wheelchair needs {needed}.",
        fix=f"Clear a {size(rule.threshold)} circle at {stop}.",
    )


def _turn_width(observation: Observation, rule: RuleSpec) -> FindingCopy:
    destination = stop_phrase(observation.facts.get("destination"))
    pivot = observation.facts.get("pivot")
    around = f"the {pivot.casefold()}" if pivot else "the corner"
    needed = inches(observation.required_inches or rule.threshold)
    shown = measured(observation.measured_inches, observation.required_inches)
    if observation.satisfied:
        return FindingCopy(
            title=f"The turn around {around} is wide enough",
            detail=f"It's {shown} at the tightest part of the turn, and a wheelchair needs {needed}.",
        )
    return FindingCopy(
        title=f"The turn around {around} is too tight",
        detail=f"It's {shown} at the tightest part of the turn. A wheelchair needs {needed} to come back round on the way to {destination}.",
        fix=f"Move {around} back, or widen the gap beside it.",
    )


def _exit_path(observation: Observation, rule: RuleSpec) -> FindingCopy:
    way_out = stop_phrase(observation.facts.get("exit"))
    if observation.satisfied:
        return FindingCopy(
            title="The way out is clear",
            detail=f"There's a path from every seat to {way_out}.",
        )
    blockers = things(observation.facts.get("blockers", []))
    subject = f"{blockers} sit" if blockers else "Something sits"
    stranded = observation.facts.get("blocked_from") or []
    origin = stop_phrase(stranded[0]) if stranded else "the seats"
    return FindingCopy(
        title="The way out is blocked",
        detail=f"{subject} across the only path from {origin} to {way_out}.",
        fix="Move enough of it aside to leave a gap all the way through.",
    )


QUESTIONS = {
    "entrance_threshold": FindingCopy(
        title="Send a photo of the front doorway from the side",
        detail="Get the floor and the bottom of the door in frame. We'll measure the step and check it against the half inch the standard allows.",
    ),
    "door_hardware": FindingCopy(
        title="Send a photo of the front door handle",
        detail="Straight on, close enough to see its shape. We'll check it opens with a closed fist and sits between 34 and 48 inches up.",
    ),
    "door_opening_force": FindingCopy(
        title="Push the front door open with one finger and tell us if it gives",
        detail="A door should open with 5 pounds of push, and one finger is about right for that.",
    ),
    "floor_surface": FindingCopy(
        title="Send a photo of the floor just inside the front door",
        detail="Include any mat. We'll check it lies flat, stays put, and that carpet is no thicker than half an inch.",
    ),
    "restroom_turning_space": FindingCopy(
        title="Send a photo of the customer restroom from the doorway",
        detail="Stand in the door and get the whole room in. We'll check there's a 60 inch circle to turn around in.",
    ),
}

WRITERS: dict[str, Callable[[Observation, RuleSpec], FindingCopy]] = {
    "route_clear_width": _route_width,
    "door_clear_width": _door_width,
    "service_counter_height": _counter_height,
    "service_counter_approach": _counter_approach,
    "passing_space": _passing_space,
    "turning_space": _turning_space,
    "turn_clear_width": _turn_width,
    "exit_path": _exit_path,
}


REQUESTS = {
    "door_clear_width": FindingCopy(
        title="Measure the front doorway and send us the number",
        detail="Open the door all the way and measure from the face of the door across to the frame. That's the width a wheelchair actually gets, and it needs 32 inches.",
    ),
}

GENERIC_REQUEST = FindingCopy(
    title="Send us one measurement and we'll finish this check",
    detail="A tape measure across the narrowest part is all it takes.",
)


def request(rule: RuleSpec) -> FindingCopy:
    """What to ask for when geometry cannot settle a rule on its own."""
    return REQUESTS.get(rule.id, GENERIC_REQUEST)


def another_look(labels: list[str]) -> FindingCopy:
    """Thin coverage becomes a request, never a red finding."""
    subject = things(labels) or "that corner"
    return FindingCopy(
        title=f"Point the phone at {subject} again",
        detail="A few seconds from a second angle is enough, then we'll measure it.",
    )


NO_ARRANGEMENT = "We couldn't find an arrangement that works."
"""The sentence the plan prescribes for an exhausted search, section 2.

It is always followed by one specific thing the owner could allow, because a
dead end with no next move is not an answer.
"""

RATIONALES = {
    "split_the_gap": "Move {what} {distance} apart.",
    "move_one_aside": "Move {what} {distance} over.",
    "stagger": "Step {what} {distance} apart along the aisle, so they stop lining up.",
    "turn_one": "Turn {what} a quarter turn.",
}

RELAXATIONS = {
    "unlock": "Can {what} be moved? Unlock it and we'll try again.",
    "set_aside": "Try it without {what}?",
}


def proposal_rationale(strategy: str, labels: list[str], inches_moved: float) -> str:
    """What the owner sees on the before and after, in one sentence."""
    template = RATIONALES.get(strategy, "Move {what} {distance}.")
    return template.format(
        what=things(labels) or "it", distance=inches(inches_moved)
    )


def relaxation_question(kind: str, labels: list[str]) -> str:
    """One specific thing to allow, phrased as a choice the owner makes."""
    return RELAXATIONS[kind].format(what=things(labels) or "one piece")


def no_arrangement(question: str | None) -> str:
    return f"{NO_ARRANGEMENT} {question}" if question else NO_ARRANGEMENT


def describe(observation: Observation, rule: RuleSpec) -> FindingCopy:
    if rule.id in QUESTIONS:
        return QUESTIONS[rule.id]
    writer = WRITERS.get(rule.id)
    if writer is None:
        raise KeyError(f"no copy written for {rule.id}")
    return writer(observation, rule)
