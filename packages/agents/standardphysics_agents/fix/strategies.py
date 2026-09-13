"""A bounded ladder of rearrangements, least disruptive first.

Each candidate is a guess. None of them is measured here, because whether a
guess opened the aisle is a question for the measurement provider, not for
arithmetic in this file. The search tries them in order and stops at the first
one that both survives the hard constraints and measures better.

Ordering by disruption is the whole point. Sliding two cases three inches apart
and turning a display case a quarter turn both fix a gap, and only one of them
is something a shop owner will actually do.
"""

from __future__ import annotations

from dataclasses import dataclass

from standardphysics_contracts import NodeMove, SceneNode, Vec3

from .moves import footprint_span
from .pinch import Pinch

SAFETY_MARGIN_METERS = 0.0127
"""Half an inch past the threshold, so a float does not land on 35.999."""

SPLIT_STEPS = (0.5, 1.0, 1.6)
"""Multiples of the shortfall, shared between both sides of the gap."""

SINGLE_STEPS = (1.0, 1.6, 2.4)
"""Multiples of the shortfall, when only one side has anywhere to go."""

STAGGER_STEPS = (1.0, 1.6, 2.4, 3.2)
"""Multiples of a node's own depth, to pull it out of the aisle sideways."""

QUARTER_TURN_DEGREES = 90.0

TURN_DISRUPTION_METERS = 1.5
"""What turning a piece of furniture costs, measured in metres of sliding.

Turning a display case is a bigger change to a shop than nudging it, so it
sorts below every slide that could do the job instead.
"""


@dataclass(frozen=True)
class Candidate:
    strategy: str
    moves: list[NodeMove]
    disruption: float


def _outward(node: SceneNode, pinch: Pinch) -> float:
    """Which way along the measurement this node sits from the gap's middle."""
    centre = node.transform.position
    side = (centre.x - pinch.centre.x) * pinch.across[0] + (
        centre.y - pinch.centre.y
    ) * pinch.across[1]
    return 1.0 if side >= 0 else -1.0


def _slide(node: SceneNode, axis: tuple[float, float], distance: float) -> NodeMove:
    return NodeMove(
        node_id=node.id,
        delta_translation=Vec3(x=axis[0] * distance, y=axis[1] * distance, z=0.0),
    )


def _distance(moves: list[NodeMove]) -> float:
    return sum(
        (move.delta_translation.x**2 + move.delta_translation.y**2) ** 0.5
        for move in moves
    )


def _candidate(strategy: str, moves: list[NodeMove], turns: int = 0) -> Candidate:
    return Candidate(
        strategy=strategy,
        moves=moves,
        disruption=_distance(moves) + turns * TURN_DISRUPTION_METERS,
    )


def _split_the_gap(pinch: Pinch) -> list[Candidate]:
    """Both sides move apart. The obvious fix, and the one owners expect."""
    if len(pinch.movable) < 2:
        return []
    needed = pinch.deficit_meters + SAFETY_MARGIN_METERS
    found = []
    for step in SPLIT_STEPS:
        moves = [
            _slide(node, pinch.across, _outward(node, pinch) * needed * step)
            for node in pinch.movable
        ]
        found.append(_candidate("split_the_gap", moves))
    return found


def _move_one_aside(pinch: Pinch) -> list[Candidate]:
    """One side carries the whole shortfall, for when the other cannot move."""
    needed = pinch.deficit_meters + SAFETY_MARGIN_METERS
    found = []
    for node in pinch.movable:
        for step in SINGLE_STEPS:
            moves = [_slide(node, pinch.across, _outward(node, pinch) * needed * step)]
            found.append(_candidate("move_one_aside", moves))
    return found


def _stagger(pinch: Pinch) -> list[Candidate]:
    """Pull the two sides past each other so the aisle is never pinched at once.

    Where both sides run to a wall, widening the gap is the one move the room
    forbids, and stepping them apart along the aisle is what is left.
    """
    if len(pinch.movable) < 2:
        return []
    depth = max(footprint_span(node, pinch.along) for node in pinch.movable)
    found = []
    for step in STAGGER_STEPS:
        distance = depth * step + SAFETY_MARGIN_METERS
        moves = [
            _slide(node, pinch.along, _outward(node, pinch) * distance)
            for node in pinch.movable
        ]
        found.append(_candidate("stagger", moves))
    return found


def _turn_one(pinch: Pinch) -> list[Candidate]:
    """A quarter turn, so a long piece stops lying across the aisle."""
    found = []
    for node in pinch.movable:
        for degrees in (QUARTER_TURN_DEGREES, -QUARTER_TURN_DEGREES):
            moves = [
                NodeMove(
                    node_id=node.id,
                    delta_translation=Vec3(x=0.0, y=0.0, z=0.0),
                    delta_rotation_z_degrees=degrees,
                )
            ]
            found.append(_candidate("turn_one", moves, turns=1))
    return found


FAMILIES = (_split_the_gap, _move_one_aside, _stagger, _turn_one)

SEALED_FAMILIES = (_stagger, _turn_one)
"""What is worth trying when there is no gap at all.

A sealed run cannot be widened. The two things forming it are already touching,
so sliding them apart along the measurement pushes each one into whatever is
behind it, at every distance. Offering those candidates anyway fills the ladder
with rearrangements that were never going to work and pushes the ones that
might off the end of it. Stepping the two past each other, or turning one, is
what opens a sealed run.
"""

PREFERENCE = ("split_the_gap", "move_one_aside", "stagger", "turn_one")
"""How ties are broken, in order.

Sliding two cases apart by half the shortfall each and sliding one of them the
whole way disturb the same total distance, so the shortfall alone cannot choose
between them. Opening a gap from both sides moves each piece less far and is
what the plan's own example asks for, so it goes first.
"""




def candidates(pinch: Pinch, limit: int = 24) -> list[Candidate]:
    """Every rearrangement worth measuring, least disruptive first."""
    if not pinch.fixable:
        return []
    found: list[Candidate] = []
    for family in SEALED_FAMILIES if pinch.sealed else FAMILIES:
        found.extend(family(pinch))
    found.sort(
        key=lambda candidate: (
            candidate.disruption,
            PREFERENCE.index(candidate.strategy),
        )
    )
    return found[:limit]
