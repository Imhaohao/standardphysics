"""The things LiDAR cannot see, turned into one specific ask each.

A scan measures shapes. It does not measure how hard a door is to push, what a
handle feels like in a closed fist, or whether the mat by the door is stuck
down. Each of those becomes a single request for one piece of evidence, written
as the thing to do rather than as the thing we are missing.
"""

from __future__ import annotations

from typing import Callable

from standardphysics_contracts import SceneGraph, SceneNode

from ..tracing import traced
from . import roles
from .context import CheckContext
from .observation import Observation

NodeFinder = Callable[[SceneGraph], list[SceneNode]]


def _entrance_nodes(graph: SceneGraph) -> list[SceneNode]:
    door = roles.entrance(graph)
    return [door] if door else []


def _floor_nodes(graph: SceneGraph) -> list[SceneNode]:
    return roles.floors(graph)[:1]


def _no_nodes(graph: SceneGraph) -> list[SceneNode]:
    return []


ASK_ABOUT: tuple[tuple[str, NodeFinder], ...] = (
    ("entrance_threshold", _entrance_nodes),
    ("door_hardware", _entrance_nodes),
    ("door_opening_force", _entrance_nodes),
    ("floor_surface", _floor_nodes),
    ("restroom_turning_space", _no_nodes),
)

RULE_IDS = frozenset(rule_id for rule_id, _ in ASK_ABOUT)


@traced("check.scan_cannot_see")
def scan_cannot_see(ctx: CheckContext) -> list[Observation]:
    return [_ask(ctx, rule_id, finder) for rule_id, finder in ASK_ABOUT]


def _ask(ctx: CheckContext, rule_id: str, finder: NodeFinder) -> Observation:
    rule = ctx.rule(rule_id)
    nodes = finder(ctx.graph)
    return Observation(
        rule_id=rule_id,
        satisfied=False,
        measured_inches=None,
        required_inches=rule.threshold if rule.unit == "in" else None,
        relied_on=tuple(node.id for node in nodes),
        locus=None,
        facts={
            "subject": nodes[0].label if nodes else None,
            "evidence": rule.evidence,
        },
        dedupe_key=(rule_id,),
        reason=f"needs_{rule.evidence}",
    )
