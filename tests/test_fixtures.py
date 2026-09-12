"""The fixture shop is the contract three lanes develop against.

If these fail, Lane C's checks and Lane B's measurements are testing against
different geometry than they think.
"""

from standardphysics_contracts import to_inches, to_meters
from standardphysics_fixtures import (
    FIX_SHIFT_INCHES,
    FixtureMeasurements,
    PINCH_INCHES,
    build_graph,
    build_scenario,
    node_id,
)


def test_graph_builds():
    graph = build_graph()
    assert len(graph.nodes) == 19
    assert len(graph.movable()) == 12


def test_counter_and_walls_are_fixed():
    graph = build_graph()
    assert not graph.by_id(node_id("counter")).movable
    assert not graph.by_id(node_id("wall_north")).movable


def test_display_cases_leave_exactly_the_pinch():
    graph = build_graph()
    west = graph.by_id(node_id("case_west"))
    east = graph.by_id(node_id("case_east"))
    gap = (east.transform.position.x - east.dimensions.x / 2) - (
        west.transform.position.x + west.dimensions.x / 2
    )
    assert round(to_inches(gap), 6) == PINCH_INCHES


def test_route_measures_the_pinch_and_names_both_cases():
    graph, scenario = build_graph(), build_scenario()
    result = FixtureMeasurements().route_clear_width(graph, scenario, 0)
    assert round(result.inches, 6) == PINCH_INCHES
    assert set(result.blocking_node_ids) == {node_id("case_west"), node_id("case_east")}


def test_pinch_point_sits_between_the_cases():
    graph, scenario = build_graph(), build_scenario()
    point = FixtureMeasurements().route_clear_width(graph, scenario, 0).pinch_point
    assert abs(point.x) < 1e-9
    assert abs(point.y) < 1e-9


def test_the_documented_fix_reaches_thirty_six_inches():
    graph, scenario = build_graph(), build_scenario()
    graph.by_id(node_id("case_east")).transform.m[3] += to_meters(FIX_SHIFT_INCHES)
    result = FixtureMeasurements().route_clear_width(graph, scenario, 0)
    assert round(result.inches, 6) == 36.0


def test_overlapping_obstacles_do_not_read_as_a_passage():
    """Tables sit inside the display cases' span. A naive gap search finds a
    phantom 85-inch opening there."""
    graph, scenario = build_graph(), build_scenario()
    result = FixtureMeasurements().route_clear_width(graph, scenario, 0)
    assert result.inches < 40.0
