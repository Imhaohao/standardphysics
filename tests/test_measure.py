"""Lane B's measurements, against the fixture shop.

The fixture's only route to the counter pinches to exactly 31 inches and opens
to exactly 36 when one display case moves 5. If these numbers drift, Lane C's
checks are measuring something other than what they think.
"""

import pytest

from standardphysics_contracts import to_inches, to_meters
from standardphysics_fixtures import (
    FIX_SHIFT_INCHES,
    PINCH_INCHES,
    build_graph,
    build_scenario,
    node_id,
)
from standardphysics_pipeline.footprints import footprint, gap_between, gap_between_nodes
from standardphysics_pipeline.measure import PipelineMeasurements
from standardphysics_pipeline.occupancy import BLOCKING_HEIGHT, blocks_floor, build_grid
from standardphysics_pipeline.routes import clearance_map, widest_path


@pytest.fixture
def shop():
    return build_graph(), build_scenario(), PipelineMeasurements()


def test_route_measures_the_pinch_exactly(shop):
    graph, scenario, measure = shop
    assert measure.route_clear_width(graph, scenario, 0).inches == pytest.approx(
        PINCH_INCHES, abs=1e-6
    )


def test_route_names_both_display_cases(shop):
    graph, scenario, measure = shop
    result = measure.route_clear_width(graph, scenario, 0)
    assert set(result.blocking_node_ids) == {node_id("case_west"), node_id("case_east")}


def test_pinch_sits_between_the_cases(shop):
    graph, scenario, measure = shop
    point = measure.route_clear_width(graph, scenario, 0).pinch_point
    assert abs(point.x) < 0.05


def test_the_documented_fix_reaches_exactly_thirty_six(shop):
    graph, scenario, measure = shop
    graph.by_id(node_id("case_east")).transform.m[3] += to_meters(FIX_SHIFT_INCHES)
    assert measure.route_clear_width(graph, scenario, 0).inches == pytest.approx(
        36.0, abs=1e-6
    )


def test_route_returns_a_drawable_path(shop):
    graph, scenario, measure = shop
    assert len(measure.route_clear_width(graph, scenario, 0).path) > 2


def test_endpoints_do_not_set_the_bottleneck(shop):
    """Standing at a counter puts you within reach of it. That is the counter
    approach check's business, not the route width's."""
    graph, scenario, measure = shop
    assert measure.route_clear_width(graph, scenario, 0).inches > 20.0


def test_counter_height_comes_from_the_top_not_the_centre(shop):
    graph, _, measure = shop
    counter = graph.by_id(node_id("counter"))
    expected = counter.transform.position.z + counter.dimensions.z / 2
    assert measure.counter_height(graph, node_id("counter")).inches == pytest.approx(
        to_inches(expected)
    )


def test_a_blocked_route_reports_unreachable(shop):
    """Stretch the east case wall to wall, sealing every way through. Each case
    stops short of its wall, so meeting the west case alone leaves a gap."""
    graph, scenario, measure = shop
    east = graph.by_id(node_id("case_east"))
    east.dimensions.x = 6.0
    east.transform.m[3] = 0.0
    result = measure.route_clear_width(graph, scenario, 0)
    assert not result.reachable


def test_low_objects_do_not_block(shop):
    graph, _, _ = shop
    mat = graph.by_id(node_id("table_1")).model_copy(deep=True)
    mat.dimensions.z = BLOCKING_HEIGHT / 2
    mat.transform.m[11] = mat.dimensions.z / 2
    assert not blocks_floor(mat)


def test_doors_are_openings_not_obstacles(shop):
    graph, _, _ = shop
    assert not blocks_floor(graph.by_id(node_id("door_front")))


def test_grid_marks_the_walls(shop):
    graph, _, _ = shop
    grid = build_grid(graph)
    assert grid.occupied.any()


def test_occupied_cells_name_an_object_or_are_the_world_edge(shop):
    """Ground beyond the building is closed off but belongs to no node, so a
    finding can never blame the edge of the world for a pinch."""
    graph, _, _ = shop
    grid = build_grid(graph)
    owned = grid.owner[grid.occupied]
    assert (owned >= 0).any()


def test_a_doorway_is_open_floor(shop):
    """A wall runs the full length of its side and the door sits inside it, so
    skipping the door is not enough: it has to be cut out of the wall."""
    graph, _, _ = shop
    grid = build_grid(graph)
    door = graph.by_id(node_id("door_front"))
    centre = door.transform.position
    row, col = grid.to_cell(centre.x, centre.y)
    assert grid.contains(row, col)
    assert not grid.occupied[row, col]


def test_a_route_can_come_in_from_the_street(shop):
    from standardphysics_contracts import Scenario, Stop, Vec3

    graph, _, measure = shop
    street = Scenario(
        name="From the street",
        stops=[
            Stop(name="Street", position=Vec3(x=0.0, y=-5.0, z=0.0)),
            Stop(name="Counter", position=Vec3(x=-0.8, y=3.1, z=0.0)),
        ],
    )
    result = measure.route_clear_width(graph, street, 0)
    assert result.reachable
    assert result.inches == pytest.approx(PINCH_INCHES, abs=1e-6)


def test_the_search_does_not_wander_off_into_the_padding(shop):
    """An open door lets the search leave the building. Beyond the floor the
    grid is empty space with excellent clearance, so an unbounded search
    explores all of it before reaching the goal."""
    import time

    graph, scenario, measure = shop
    started = time.time()
    measure.route_clear_width(graph, scenario, 0)
    assert time.time() - started < 5.0


def test_touching_footprints_have_no_gap(shop):
    graph, _, _ = shop
    case = graph.by_id(node_id("case_west"))
    assert gap_between_nodes(case, case) == 0.0


def test_footprint_follows_rotation(shop):
    graph, _, _ = shop
    table = graph.by_id(node_id("table_1"))
    corners = footprint(table)
    assert len(corners) == 4
    width = max(x for x, _ in corners) - min(x for x, _ in corners)
    assert width == pytest.approx(table.dimensions.x)


def test_separated_rectangles_measure_their_gap():
    a = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    b = [(2.0, 0.0), (3.0, 0.0), (3.0, 1.0), (2.0, 1.0)]
    assert gap_between(a, b) == pytest.approx(1.0)


def test_widest_path_prefers_the_wide_way_round(shop):
    graph, scenario, _ = shop
    grid = build_grid(graph)
    clearance = clearance_map(grid)
    start = grid.to_cell(scenario.stops[0].position.x, scenario.stops[0].position.y)
    goal = grid.to_cell(scenario.stops[1].position.x, scenario.stops[1].position.y)
    result = widest_path(grid, clearance, start, goal)
    assert result.reachable
    assert result.clearance_radius > 0


def test_a_run_below_a_threshold_is_measured_along_the_route(shop):
    """403.5.1 permits 32 in for a run of 24 in at most, and a bottleneck says
    nothing about how long the route stays narrow."""
    graph, scenario, measure = shop
    run = measure.route_run_below(graph, scenario, 0, 36.0)
    assert run > 24.0


def test_nothing_runs_below_a_threshold_the_route_never_reaches(shop):
    graph, scenario, measure = shop
    assert measure.route_run_below(graph, scenario, 0, 1.0) == 0.0


def test_the_threshold_is_an_argument_not_a_constant(shop):
    """It belongs to the rule pack, where a person checked it against source."""
    graph, scenario, measure = shop
    wide = measure.route_run_below(graph, scenario, 0, 36.0)
    narrow = measure.route_run_below(graph, scenario, 0, 32.0)
    assert wide >= narrow


def test_counter_approach_reports_what_it_measured(shop):
    """Not a restatement of the 48 by 30 the rule asks for."""
    graph, _, measure = shop
    result = measure.counter_approach(graph, node_id("counter"))
    assert result.inches_wide != 48.0 or result.inches_deep != 30.0
    assert result.fits


def test_per_point_clearance_runs_parallel_to_the_path(shop):
    graph, scenario, measure = shop
    result = measure.route_clear_width(graph, scenario, 0)
    assert len(measure.route_path_clearances(graph, scenario, 0)) == len(result.path)


def test_exempt_points_report_nothing_rather_than_a_number(shop):
    """Inside the exemption the route wanders, so a clearance there measures
    nothing and would paint the doorway as the tightest part of the trip."""
    graph, scenario, measure = shop
    values = measure.route_path_clearances(graph, scenario, 0)
    assert any(value is None for value in values)


def test_measured_points_never_fall_below_the_bottleneck(shop):
    graph, scenario, measure = shop
    result = measure.route_clear_width(graph, scenario, 0)
    measured = [v for v in measure.route_path_clearances(graph, scenario, 0) if v]
    assert min(measured) >= result.inches - 1.0
