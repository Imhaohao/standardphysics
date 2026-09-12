"""One gap is one finding, however many journeys pass through it.

The route from the door to the counter and the route from pickup back to a seat
squeeze between the same two display cases. That is one thing to move, so it is
one card in the list, and the copy names the tighter of the two measurements.
"""

from __future__ import annotations

from ..rules import AgentRulePack
from .observation import Observation


def dedupe(observations: list[Observation], rules: AgentRulePack) -> list[Observation]:
    kept: dict[tuple, Observation] = {}
    order: list[tuple] = []
    for observation in observations:
        key = observation.dedupe_key or (observation.rule_id, len(order))
        if key not in kept:
            kept[key] = observation
            order.append(key)
        elif _more_severe(observation, kept[key], rules):
            kept[key] = observation
    return [kept[key] for key in order]


def _more_severe(
    candidate: Observation, current: Observation, rules: AgentRulePack
) -> bool:
    if candidate.satisfied != current.satisfied:
        return not candidate.satisfied
    return _severity(candidate, rules) > _severity(current, rules)


def _severity(observation: Observation, rules: AgentRulePack) -> float:
    """How far past the threshold this answer sits, in inches."""
    if observation.measured_inches is None or observation.required_inches is None:
        return float("inf")
    gap = observation.required_inches - observation.measured_inches
    if rules.by_id(observation.rule_id).comparison == "at_most":
        return -gap
    return gap
