"""ADA 2010 403.5.2, the 180 degree turn.

The fixture shop has a straight route, so these build a U-shaped one: a
partition running most of the way across the room, forcing customers around
its end to reach the counter.
"""

import uuid

import pytest

from standardphysics_contracts import Mat4, Scenario, SceneGraph, SceneNode, Stop, Vec3
from standardphysics_pipeline.measure import PipelineMeasurements
from standardphysics_pipeline.turns import (
    APPROACH_REQUIRED,
    AT_TURN_REQUIRED,
    Turn,
    find_turn,
)


def node(name, centre, dims, kind="object", movable=False):
    return SceneNode(
        id=uuid.uuid5(uuid.NAMESPACE_OID, name),
        kind=kind,
        label=name,
        raw_category=name,
        dimensions=Vec3(x=dims[0], y=dims[1], z=dims[2]),
        transform=Mat4.translation(*centre),
        movable=movable,
    )


def u_shaped_shop(gap_from_east_wall: float) -> SceneGraph:
    """A partition from the west wall, leaving a gap at the east end."""
    width, depth, height = 6.0, 8.0, 3.0
    partition_length = width - 0.05 - gap_from_east_wall
    partition_centre = -width / 2 + 0.05 + partition_length / 2

    nodes = [
        node("floor", (0, 0, 0), (width, depth, 0.01), kind="floor"),
        node("wall_s", (0, -depth / 2, height / 2), (width, 0.1, height), kind="wall"),
        node("wall_n", (0, depth / 2, height / 2), (width, 0.1, height), kind="wall"),
        node("wall_w", (-width / 2, 0, height / 2), (0.1, depth, height), kind="wall"),
        node("wall_e", (width / 2, 0, height / 2), (0.1, depth, height), kind="wall"),
        node("partition", (partition_centre, 0.0, 0.6), (partition_length, 0.3, 1.2)),
    ]
    return SceneGraph(scan_id=uuid.uuid4(), nodes=nodes)


def scenario_across_the_partition() -> Scenario:
    return Scenario(
        name="Order a drink",
        stops=[
            Stop(name="Entrance", position=Vec3(x=-2.0, y=-3.4, z=0.0)),
            Stop(name="Counter", position=Vec3(x=-2.0, y=3.4, z=0.0)),
        ],
    )


@pytest.fixture
def narrow_turn():
    graph = u_shaped_shop(gap_from_east_wall=1.0)
    return graph, scenario_across_the_partition(), PipelineMeasurements()


def test_a_straight_run_has_no_turn():
    points = [Vec3(x=0.0, y=y / 10, z=0.0) for y in range(40)]
    assert find_turn(points) is None


def test_a_route_round_a_partition_has_one(narrow_turn):
    graph, scenario, measure = narrow_turn
    assert measure.turn_detail(graph, scenario, 0) is not None


def test_the_turn_reports_three_zones(narrow_turn):
    graph, scenario, measure = narrow_turn
    turn = measure.turn_detail(graph, scenario, 0)
    assert turn.approach_inches > 0
    assert turn.at_turn_inches > 0
    assert turn.leaving_inches > 0


def test_the_turn_names_what_it_goes_around(narrow_turn):
    graph, scenario, measure = narrow_turn
    turn = measure.turn_detail(graph, scenario, 0)
    assert turn.pivot_id is not None


def test_a_wide_turn_is_exempt():
    """The rule does not apply where there is 60 inches at the turn."""
    turn = Turn(
        pivot_id=uuid.uuid4(),
        pivot_width_inches=12.0,
        approach_inches=40.0,
        at_turn_inches=72.0,
        leaving_inches=40.0,
        apex=Vec3(x=0, y=0, z=0),
    )
    assert not turn.in_scope
    assert turn.passes


def test_a_wide_pivot_is_out_of_scope():
    """403.5.2 applies around an element narrower than 48 inches."""
    turn = Turn(
        pivot_id=uuid.uuid4(),
        pivot_width_inches=60.0,
        approach_inches=36.0,
        at_turn_inches=36.0,
        leaving_inches=36.0,
        apex=Vec3(x=0, y=0, z=0),
    )
    assert not turn.in_scope


def test_a_tight_turn_round_a_narrow_pivot_fails():
    turn = Turn(
        pivot_id=uuid.uuid4(),
        pivot_width_inches=12.0,
        approach_inches=44.0,
        at_turn_inches=40.0,
        leaving_inches=44.0,
        apex=Vec3(x=0, y=0, z=0),
    )
    assert turn.in_scope
    assert not turn.passes


def test_the_binding_measurement_is_the_worst_shortfall():
    turn = Turn(
        pivot_id=uuid.uuid4(),
        pivot_width_inches=12.0,
        approach_inches=38.0,
        at_turn_inches=47.0,
        leaving_inches=44.0,
        apex=Vec3(x=0, y=0, z=0),
    )
    measured, required = turn.binding_measurement
    assert (measured, required) == (38.0, APPROACH_REQUIRED)


def test_a_turn_meeting_every_threshold_passes():
    turn = Turn(
        pivot_id=uuid.uuid4(),
        pivot_width_inches=12.0,
        approach_inches=APPROACH_REQUIRED,
        at_turn_inches=AT_TURN_REQUIRED,
        leaving_inches=APPROACH_REQUIRED,
        apex=Vec3(x=0, y=0, z=0),
    )
    assert turn.in_scope
    assert turn.passes


def test_turn_clear_width_falls_back_on_a_straight_leg():
    """No 180 means the rule does not apply, so return a true number rather
    than a zero a caller might read as a failure."""
    from standardphysics_fixtures import build_graph, build_scenario

    measure = PipelineMeasurements()
    graph, scenario = build_graph(), build_scenario()
    assert measure.turn_clear_width(graph, scenario, 0).inches == pytest.approx(31.0)
