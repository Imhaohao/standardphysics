"""Regressions for the Lane B findings in PROGRESS.md.

Each test is a case that returned the wrong answer before its fix.
"""

import uuid

import pytest

from standardphysics_contracts import Mat4, SceneNode, Vec3, to_meters
from standardphysics_fixtures import PINCH_INCHES, build_graph, build_scenario, node_id
from standardphysics_pipeline.footprints import footprint
from standardphysics_pipeline.ingest import parse_room_json
from standardphysics_pipeline.measure import PipelineMeasurements


def _planter_across_leg_zero(distance_m: float, height_m: float) -> SceneNode:
    entrance = build_scenario().stops[0].position
    return SceneNode(
        id=uuid.uuid4(),
        kind="object",
        label="Planter",
        raw_category="storage",
        dimensions=Vec3(x=8.0, y=0.3, z=height_m),
        transform=Mat4.translation(entrance.x, entrance.y + distance_m, height_m / 2),
        movable=True,
    )


def test_a5_a_low_solid_obstruction_blocks_the_route():
    graph, scenario = build_graph(), build_scenario()
    graph.nodes.append(_planter_across_leg_zero(1.2, 0.2))
    assert not PipelineMeasurements().route_clear_width(graph, scenario, 0).reachable


def test_a7_resizing_an_object_rebuilds_the_cached_grid():
    graph, scenario = build_graph(), build_scenario()
    measure = PipelineMeasurements()
    measure.route_clear_width(graph, scenario, 0)
    graph.by_id(node_id("case_east")).dimensions.x += 2 * to_meters(PINCH_INCHES) + 0.05
    assert not measure.route_clear_width(graph, scenario, 0).reachable


def test_a8_counter_approach_turns_with_the_counter():
    graph = build_graph()
    counter = graph.by_id(node_id("counter"))
    matrix = counter.transform.m
    matrix[0], matrix[1], matrix[4], matrix[5] = 0.0, -1.0, 1.0, 0.0
    centre = PipelineMeasurements().counter_approach(graph, node_id("counter")).center
    xs = [x for x, _ in footprint(counter)]
    ys = [y for _, y in footprint(counter)]
    inside = min(xs) < centre.x < max(xs) and min(ys) < centre.y < max(ys)
    assert not inside


def test_a8_an_unrotated_counter_approach_is_unchanged():
    graph = build_graph()
    counter = graph.by_id(node_id("counter"))
    centre = PipelineMeasurements().counter_approach(graph, node_id("counter")).center
    position = counter.transform.position
    expected_y = position.y - counter.dimensions.y / 2 - to_meters(30.0) / 2
    assert (centre.x, centre.y) == pytest.approx((position.x, expected_y))


def test_a11_a_missing_confidence_needs_another_look():
    element = {
        "identifier": str(uuid.uuid4()),
        "dimensions": [1.0, 1.0, 1.0],
        "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
        "category": "table",
    }
    assert parse_room_json({"objects": [element]}).nodes[0].quality == "needs_another_look"
