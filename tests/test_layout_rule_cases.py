"""The server's drag check reaches the verdicts the browser's drag is held to.

The workspace slides a dragged piece along whatever it would run into, using a
TypeScript port of the hard constraints in `standardphysics_agents.fix.constraints`.
packages/fixtures/standardphysics_fixtures/data/layout_rule_cases.json lists small
rooms, moves and the verdict each must get. apps/web/src/lib/layout-rule-cases.test.ts
holds the port to them, and this holds `plan_candidate`, the check behind
POST /layout-checks, to the same ones, so the two cannot drift apart unnoticed.

Two kinds of case wait on the server. `door_keep_clear` lays a door's square
along the world's axes rather than the door's own, which a separate fix is
correcting, so cases with a turned door run only once it does. And
`_as_scanned` compares positions only, so it forgives a piece turned in place
into a wall at its scanned spot; that case is expected to fail until it does
not.
"""

from __future__ import annotations

import json
import math
import pathlib
import uuid

import pytest
import standardphysics_fixtures
from standardphysics_agents.fix.constraints import door_keep_clear
from standardphysics_contracts import Mat4, NodeMove, SceneGraph, SceneNode, Vec3

from standardphysics_api.layout import plan_candidate

CASES = json.loads(
    (pathlib.Path(standardphysics_fixtures.__path__[0]) / "data" / "layout_rule_cases.json").read_text(encoding="utf-8")
)
BROWSER_REASONS = frozenset({"collided", "blocked_a_door", "left_the_floor", "moved_too_far"})


def _id(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"layout-rule-cases/{name}")


def _transform(at: list[float], degrees: float) -> Mat4:
    cos_t, sin_t = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    x, y, z = at
    return Mat4(m=[cos_t, -sin_t, 0.0, x, sin_t, cos_t, 0.0, y, 0.0, 0.0, 1.0, z, 0.0, 0.0, 0.0, 1.0])


def _node(piece: dict) -> SceneNode:
    width, depth, height = piece["size"]
    measured = piece.get("measured")
    return SceneNode(
        id=_id(piece["id"]), kind=piece["kind"], label=piece.get("label", piece["id"]),
        raw_category=piece.get("raw_category", piece["kind"]), dimensions=Vec3(x=width, y=depth, z=height),
        transform=_transform(piece["at"], piece.get("turn", 0.0)), movable=piece.get("movable", False),
        measured_position=Vec3(x=measured[0], y=measured[1], z=piece["at"][2]) if measured else None,
    )


def _room(name: str) -> SceneGraph:
    return SceneGraph(scan_id=_id(name), revision=0, nodes=[_node(piece) for piece in CASES["rooms"][name]])


def _verdict(room: str, node: str, to: list[float], turn: float = 0.0) -> list[list[str]]:
    """What the drag check says when `node` is moved so its centre is at `to`, as (piece, reason) pairs."""
    base = _room(room)
    at = base.by_id(_id(node)).transform.position
    move = NodeMove(
        node_id=_id(node), delta_translation=Vec3(x=to[0] - at.x, y=to[1] - at.y, z=0.0), delta_rotation_z_degrees=turn,
    )
    _, blocked = plan_candidate(base, [move], construction=True)
    names = {str(_id(piece["id"])): piece["id"] for piece in CASES["rooms"][room]}
    return sorted({(names[found.node_id], found.reason) for found in blocked if found.reason in BROWSER_REASONS})


def _turned_door_zone_follows_the_door() -> bool:
    """Whether `door_keep_clear` lays a door's square in the door's own frame yet."""
    door = _node({"id": "probe", "kind": "door", "at": [0, 0, 1], "size": [0.9, 0.05, 2], "turn": 90})
    zone = door_keep_clear(door)
    xs, ys = [x for x, _ in zone], [y for _, y in zone]
    return max(xs) - min(xs) > max(ys) - min(ys)


SERVER_TURNS_DOOR_ZONES = _turned_door_zone_follows_the_door()
TURNED_DOOR = "door_keep_clear lays the square along the world's axes until the fix for turned doors lands"
TURN_IN_PLACE = "_as_scanned forgives a piece turned in place at its scanned spot, so the server lets it into the wall"


def _marks(case: dict) -> list:
    marks = []
    if case.get("turned_door") and not SERVER_TURNS_DOOR_ZONES:
        marks.append(pytest.mark.skip(reason=TURNED_DOOR))
    if case.get("server_forgives_turns"):
        marks.append(pytest.mark.xfail(strict=True, reason=TURN_IN_PLACE))
    return marks


def _cases(kind: str) -> list:
    return [pytest.param(case, id=case["name"], marks=_marks(case)) for case in CASES[kind]]


@pytest.mark.parametrize("case", _cases("verdicts"))
def test_the_server_reaches_the_browsers_verdict(case):
    expected = sorted((piece, reason) for piece, reason in case["blocked"])
    assert _verdict(case["room"], case["node"], case["to"], case.get("turn", 0.0)) == expected


@pytest.mark.parametrize("case", _cases("slides"))
def test_the_server_allows_where_a_slide_lands_and_refuses_just_past_it(case):
    assert _verdict(case["room"], case["node"], case["lands"]) == []
    assert _verdict(case["room"], case["node"], case["past"]) == [(case["node"], case["refused"])]


def test_every_room_a_case_names_exists():
    named = {case["room"] for kind in ("verdicts", "slides") for case in CASES[kind]}
    assert named <= set(CASES["rooms"])
