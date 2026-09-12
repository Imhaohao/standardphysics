"""Small edits to the fixture shop, for building labelled cases.

These write dimensions, which no agent in the loop may do. They are not in the
loop: this is fixture construction, the same thing `packages/fixtures` does,
and the cases it produces are synthetic by declaration rather than measured.
"""

from __future__ import annotations

from uuid import UUID

from standardphysics_contracts import (
    Mat4,
    Scenario,
    SceneGraph,
    SceneNode,
    Stop,
    Vec3,
    to_meters,
)
from standardphysics_fixtures import build_graph
from standardphysics_fixtures.shop import (
    CASE_DEPTH,
    CASE_HEIGHT,
    CASE_WALL_GAP_INCHES,
    ROOM_WIDTH,
    WALL_THICKNESS,
    node_id,
)

CASE_OUTER_EDGE = (
    ROOM_WIDTH / 2 - WALL_THICKNESS / 2 - to_meters(CASE_WALL_GAP_INCHES)
)
"""Where a display case stops, short of its wall. The fixture leaves this room
so a case has somewhere to slide."""

CASE_WEST = node_id("case_west")
CASE_EAST = node_id("case_east")
COUNTER = node_id("counter")
DOOR = node_id("door_front")
FLOOR = node_id("floor")


def replace(graph: SceneGraph, node_id_: UUID, **updates) -> SceneGraph:
    return graph.model_copy(
        update={
            "nodes": [
                node.model_copy(update=updates) if node.id == node_id_ else node
                for node in graph.nodes
            ]
        }
    )


def drop(graph: SceneGraph, *node_ids: UUID) -> SceneGraph:
    removed = set(node_ids)
    return graph.model_copy(
        update={"nodes": [n for n in graph.nodes if n.id not in removed]}
    )


def add(graph: SceneGraph, *nodes: SceneNode) -> SceneGraph:
    return graph.model_copy(update={"nodes": [*graph.nodes, *nodes]})


def pin(graph: SceneGraph, *node_ids: UUID) -> SceneGraph:
    for node_id_ in node_ids:
        graph = replace(graph, node_id_, movable=False)
    return graph


def set_quality(graph: SceneGraph, node_id_: UUID, quality: str) -> SceneGraph:
    return replace(graph, node_id_, quality=quality)


def relabel(graph: SceneGraph, node_id_: UUID, label: str) -> SceneGraph:
    return replace(graph, node_id_, label=label)


def aisle(graph: SceneGraph, inches: float) -> SceneGraph:
    """Set the gap between the display cases, the way the fixture builds them.

    Each case is rebuilt to run from its own outer edge to the edge of the gap,
    so widening the aisle shortens the cases rather than pushing one through a
    wall.
    """
    inner = to_meters(inches) / 2
    width = CASE_OUTER_EDGE - inner
    centre = inner + width / 2
    dimensions = Vec3(x=width, y=CASE_DEPTH, z=CASE_HEIGHT)
    for node_id_, sign in ((CASE_WEST, -1.0), (CASE_EAST, 1.0)):
        graph = replace(
            graph,
            node_id_,
            dimensions=dimensions,
            transform=Mat4.translation(sign * centre, 0.0, CASE_HEIGHT / 2),
        )
    return graph


def door_width(graph: SceneGraph, inches: float) -> SceneGraph:
    door = graph.by_id(DOOR)
    return replace(
        graph,
        DOOR,
        dimensions=Vec3(x=to_meters(inches), y=door.dimensions.y, z=door.dimensions.z),
    )


def counter_height(graph: SceneGraph, inches: float) -> SceneGraph:
    counter = graph.by_id(COUNTER)
    height = to_meters(inches)
    return replace(
        graph,
        COUNTER,
        dimensions=Vec3(x=counter.dimensions.x, y=counter.dimensions.y, z=height),
        transform=Mat4.translation(
            counter.transform.position.x, counter.transform.position.y, height / 2
        ),
    )


def box(
    name: str,
    label: str,
    centre: tuple[float, float, float],
    dims: tuple[float, float, float],
    *,
    kind: str = "object",
    movable: bool = True,
    raw_category: str = "storage",
) -> SceneNode:
    return SceneNode(
        id=node_id(name),
        kind=kind,
        label=label,
        raw_category=raw_category,
        dimensions=Vec3(x=dims[0], y=dims[1], z=dims[2]),
        transform=Mat4.translation(*centre),
        movable=movable,
    )


def open_shop() -> SceneGraph:
    """The fixture with the display cases gone, so the floor is clear."""
    return drop(build_graph(), CASE_WEST, CASE_EAST)


def errand(name: str, there: Vec3, back: Vec3) -> Scenario:
    """Out and back the same way, which is what makes a stop a dead end."""
    return Scenario(
        name=name,
        stops=[
            Stop(name="Entrance", position=back),
            Stop(name=name, position=there),
            Stop(name="Exit", position=back),
        ],
    )


COUNTER_SIDE = (
    "table_1", "table_2", "chair_1", "chair_2", "chair_3", "chair_4",
)
"""The seating between the display cases and the counter."""


def clear_counter_side(graph: SceneGraph) -> SceneGraph:
    """Take out the seating that crowds the counter.

    The fixture leaves a 0.75 m band between the counter face and the nearest
    tables, which is a real 29.8 in pinch and the tightest thing on most legs.
    A case testing an aisle wants the aisle to be the tightest thing in the
    room, so it clears this first and tests one dimension at a time.
    """
    return drop(graph, *[node_id(name) for name in COUNTER_SIDE])
