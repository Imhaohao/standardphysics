"""What a rearrangement is not allowed to do.

Plan section 10 names the hard constraints: walls, built-in counters, doors and
their swing, the floor boundary, confirmed sizes, owner locks, and the checks
themselves. The checks are enforced by re-running them. Everything else is
enforced here, before a candidate is measured at all, because a candidate that
puts a display case inside a wall has an excellent clear width and is not a
rearrangement anybody can carry out.
"""

from __future__ import annotations

from dataclasses import dataclass

from standardphysics_contracts import SceneGraph, SceneNode, Vec3
from standardphysics_pipeline import footprint, gap_between
from standardphysics_pipeline.footprints import Polygon
from standardphysics_pipeline.occupancy import blocks_floor

from ..hashing import inventory

FLOOR_MARGIN = 0.01
"""A centimetre of slack at the floor edge, for arithmetic rather than for room."""

OVERLAP_TOLERANCE = 0.005
"""How far two things may interpenetrate before it counts as a collision.

`gap_between` returns zero for touching and for overlapping alike, and plenty
of shop furniture is built flush against a wall. Testing a footprint shrunk by
5 mm separates the two cases: touching leaves a 5 mm gap, real overlap leaves
none. 5 mm is a fifth of an inch, well under anything a scan resolves.

The shrunk shape is a test shape. Nothing proposed is ever built from it.
"""

SWING_KINDS = frozenset({"door"})


@dataclass(frozen=True)
class Violation:
    kind: str
    node_id: str
    detail: str


def _moved_nodes(base: SceneGraph, candidate: SceneGraph) -> list[SceneNode]:
    before = {node.id: node for node in base.nodes}
    return [
        node
        for node in candidate.nodes
        if node.id in before and node.transform.m != before[node.id].transform.m
    ]


def _locked_moves(base: SceneGraph, candidate: SceneGraph) -> list[Violation]:
    before = {node.id: node for node in base.nodes}
    return [
        Violation("moved_something_fixed", str(node.id), node.label)
        for node in _moved_nodes(base, candidate)
        if not before[node.id].movable
    ]


def _resizes(base: SceneGraph, candidate: SceneGraph) -> list[Violation]:
    before = {node.id: node for node in base.nodes}
    found = []
    for node in candidate.nodes:
        original = before.get(node.id)
        if original and node.dimensions != original.dimensions:
            found.append(Violation("resized", str(node.id), node.label))
    return found


def _inventory_changes(base: SceneGraph, candidate: SceneGraph) -> list[Violation]:
    was, now = inventory(base), inventory(candidate)
    return [
        Violation("inventory_changed", label, f"{was.get(label, 0)} -> {now.get(label, 0)}")
        for label in sorted(set(was) | set(now))
        if was.get(label, 0) != now.get(label, 0)
    ]


def floor_bounds(graph: SceneGraph) -> tuple[float, float, float, float] | None:
    for node in graph.nodes:
        if node.kind == "floor":
            centre = node.transform.position
            half_x, half_y = node.dimensions.x / 2, node.dimensions.y / 2
            return (
                centre.x - half_x,
                centre.y - half_y,
                centre.x + half_x,
                centre.y + half_y,
            )
    return None


def _off_the_floor(candidate: SceneGraph, moved: list[SceneNode]) -> list[Violation]:
    bounds = floor_bounds(candidate)
    if bounds is None:
        return []
    min_x, min_y, max_x, max_y = bounds
    found = []
    for node in moved:
        for x, y in footprint(node):
            if not (
                min_x - FLOOR_MARGIN <= x <= max_x + FLOOR_MARGIN
                and min_y - FLOOR_MARGIN <= y <= max_y + FLOOR_MARGIN
            ):
                found.append(Violation("left_the_floor", str(node.id), node.label))
                break
    return found


def door_keep_clear(door: SceneNode) -> Polygon:
    """The floor a door sweeps, as a square the width of the opening.

    A hinged door needs a quarter disc of radius equal to its width. A square
    of that side covers it and a little more, which errs toward keeping
    furniture further from a door rather than closer.
    """
    centre = door.transform.position
    reach = max(door.dimensions.x, door.dimensions.y)
    swings_along_x = door.dimensions.x >= door.dimensions.y
    half_x = reach / 2 if swings_along_x else reach
    half_y = reach if swings_along_x else reach / 2
    return [
        (centre.x - half_x, centre.y - half_y),
        (centre.x + half_x, centre.y - half_y),
        (centre.x + half_x, centre.y + half_y),
        (centre.x - half_x, centre.y + half_y),
    ]


def collision_shape(node: SceneNode, tolerance: float = OVERLAP_TOLERANCE) -> Polygon:
    """The node's footprint, pulled in on every side by `tolerance`."""
    shrunk = Vec3(
        x=max(node.dimensions.x - 2 * tolerance, 1e-6),
        y=max(node.dimensions.y - 2 * tolerance, 1e-6),
        z=node.dimensions.z,
    )
    return footprint(node.model_copy(update={"dimensions": shrunk}))


def _collisions(candidate: SceneGraph, moved: list[SceneNode]) -> list[Violation]:
    moved_ids = {node.id for node in moved}
    obstacles = [
        node
        for node in candidate.nodes
        if node.id not in moved_ids and (blocks_floor(node) or node.kind == "wall")
    ]
    swings = [(node, door_keep_clear(node)) for node in candidate.nodes
              if node.kind in SWING_KINDS]

    found = []
    for node in moved:
        found.extend(_overlaps(node, collision_shape(node), obstacles, swings))
    return found


def _overlaps(node: SceneNode, shape: Polygon, obstacles, swings) -> list[Violation]:
    for other in obstacles:
        if gap_between(shape, collision_shape(other)) == 0.0:
            return [Violation("collided", str(node.id), f"{node.label} into {other.label}")]
    for door, keep_clear in swings:
        if gap_between(shape, keep_clear) == 0.0:
            return [
                Violation(
                    "blocked_a_door", str(node.id), f"{node.label} into the {door.label}"
                )
            ]
    return []


def violations(base: SceneGraph, candidate: SceneGraph) -> list[Violation]:
    """Every hard constraint the candidate breaks, or an empty list."""
    moved = _moved_nodes(base, candidate)
    return [
        *_locked_moves(base, candidate),
        *_resizes(base, candidate),
        *_inventory_changes(base, candidate),
        *_off_the_floor(candidate, moved),
        *_collisions(candidate, moved),
    ]


def is_allowed(base: SceneGraph, candidate: SceneGraph) -> bool:
    return not violations(base, candidate)
