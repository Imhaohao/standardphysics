"""A synthetic boba shop with a deliberate 31-inch pinch.

Two display cases run from the side walls toward the middle and leave exactly
31 inches between them, on the only path from the door to the counter. That is
the finding every lane develops against, and moving one case 5 inches opens it
to the 36 inches the standard requires.

Node IDs are derived with uuid5, so they are stable across runs and safe to
reference from tests in other lanes.
"""

from __future__ import annotations

import uuid

from standardphysics_contracts import (
    Mat4,
    Scenario,
    SceneGraph,
    SceneNode,
    Stop,
    Vec3,
    to_meters,
)

NAMESPACE = uuid.UUID("6f1d2f9a-0d3f-4a1e-9b2c-000000000001")

ROOM_WIDTH = 6.0
ROOM_DEPTH = 8.0
WALL_THICKNESS = 0.1
WALL_HEIGHT = 3.0

PINCH_INCHES = 31.0
PINCH_METERS = to_meters(PINCH_INCHES)
CASE_DEPTH = 0.6
CASE_HEIGHT = 0.9

FIX_SHIFT_INCHES = 5.0
"""Moving the east case this far east opens the gap to 36 inches."""


def node_id(name: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, name)


def _box(
    name: str,
    kind: str,
    label: str,
    raw_category: str,
    center: tuple[float, float, float],
    dims: tuple[float, float, float],
    movable: bool,
) -> SceneNode:
    return SceneNode(
        id=node_id(name),
        kind=kind,
        label=label,
        raw_category=raw_category,
        dimensions=Vec3(x=dims[0], y=dims[1], z=dims[2]),
        transform=Mat4.translation(*center),
        movable=movable,
    )


def _walls() -> list[SceneNode]:
    half_w, half_d = ROOM_WIDTH / 2, ROOM_DEPTH / 2
    z = WALL_HEIGHT / 2
    spec = [
        ("wall_south", (0.0, -half_d, z), (ROOM_WIDTH, WALL_THICKNESS, WALL_HEIGHT)),
        ("wall_north", (0.0, half_d, z), (ROOM_WIDTH, WALL_THICKNESS, WALL_HEIGHT)),
        ("wall_west", (-half_w, 0.0, z), (WALL_THICKNESS, ROOM_DEPTH, WALL_HEIGHT)),
        ("wall_east", (half_w, 0.0, z), (WALL_THICKNESS, ROOM_DEPTH, WALL_HEIGHT)),
    ]
    return [_box(n, "wall", "Wall", "wall", c, d, False) for n, c, d in spec]


def _display_cases() -> list[SceneNode]:
    """Each runs from a side wall to the edge of the gap."""
    inner_edge = PINCH_METERS / 2
    wall_face = ROOM_WIDTH / 2 - WALL_THICKNESS / 2
    width = wall_face - inner_edge
    center_x = inner_edge + width / 2
    dims = (width, CASE_DEPTH, CASE_HEIGHT)
    return [
        _box("case_west", "object", "Display case", "storage",
             (-center_x, 0.0, CASE_HEIGHT / 2), dims, True),
        _box("case_east", "object", "Display case", "storage",
             (center_x, 0.0, CASE_HEIGHT / 2), dims, True),
    ]


def _furniture() -> list[SceneNode]:
    tables = [
        ("table_1", (-2.0, 2.2)), ("table_2", (2.0, 2.2)),
        ("table_3", (-2.0, -2.4)), ("table_4", (2.0, -2.4)),
    ]
    chairs = [
        ("chair_1", (-2.0, 1.5)), ("chair_2", (-2.0, 2.9)),
        ("chair_3", (2.0, 1.5)), ("chair_4", (2.0, 2.9)),
        ("chair_5", (-2.0, -3.1)), ("chair_6", (2.0, -3.1)),
    ]
    nodes = [
        _box(n, "object", "Table", "table", (x, y, 0.375), (0.6, 0.6, 0.75), True)
        for n, (x, y) in tables
    ]
    nodes += [
        _box(n, "object", "Chair", "chair", (x, y, 0.45), (0.45, 0.45, 0.9), True)
        for n, (x, y) in chairs
    ]
    return nodes


def build_graph() -> SceneGraph:
    nodes = _walls()
    nodes.append(
        _box("floor", "floor", "Floor", "floor", (0.0, 0.0, 0.0),
             (ROOM_WIDTH, ROOM_DEPTH, 0.01), False)
    )
    nodes.append(
        _box("door_front", "door", "Front door", "door",
             (0.0, -ROOM_DEPTH / 2, 1.05), (0.9, WALL_THICKNESS, 2.1), False)
    )
    nodes.append(
        _box("counter", "object", "Ordering counter", "storage",
             (0.0, 3.6, 0.55), (3.2, 0.7, 1.1), False)
    )
    nodes += _display_cases()
    nodes += _furniture()
    return SceneGraph(scan_id=node_id("scan"), revision=0, nodes=nodes)


SEAT_POSITION = (-1.3, -2.4)
"""Open floor beside table_3, where a wheelchair pulls up to the table."""


def build_scenario() -> Scenario:
    front_wall, counter = node_id("wall_south"), node_id("counter")
    return Scenario(
        name="Order a drink",
        stops=[
            Stop(name="Entrance", position=Vec3(x=0.0, y=-3.7, z=0.0),
                 anchor_node_id=front_wall),
            Stop(name="Counter", position=Vec3(x=-0.8, y=3.1, z=0.0),
                 anchor_node_id=counter),
            Stop(name="Pickup", position=Vec3(x=0.8, y=3.1, z=0.0),
                 anchor_node_id=counter),
            Stop(name="Seat", position=Vec3(x=SEAT_POSITION[0], y=SEAT_POSITION[1], z=0.0),
                 anchor_node_id=node_id("table_3")),
            Stop(name="Exit", position=Vec3(x=0.0, y=-3.7, z=0.0),
                 anchor_node_id=front_wall),
        ],
    )


def build_street_scenario() -> Scenario:
    """From the sidewalk to the counter, so a route has to cross the doorway.

    The street stop has no anchor. Nothing near it may be ignored, so the only
    way in is through the door opening itself.
    """
    return Scenario(
        name="Walk in from the street",
        stops=[
            Stop(name="Street", position=Vec3(x=0.0, y=-ROOM_DEPTH / 2 - 1.0, z=0.0)),
            Stop(name="Counter", position=Vec3(x=-0.8, y=3.1, z=0.0),
                 anchor_node_id=node_id("counter")),
        ],
    )
