"""The clearance a map of the room shows is the clearance every leg in the room is measured on.

A map drawn from any other field would disagree with the findings beside it somewhere, and the place it would
disagree first is a doorway, where the ground outside the walls counts as open floor to the plain distance transform
and as an edge to a trip held in the room.
"""

import numpy as np
import pytest
from standardphysics_contracts import to_inches
from standardphysics_fixtures import (
    build_graph,
    build_lawsuit_graph,
    build_lawsuit_scenario,
    build_scenario,
    build_street_scenario,
)
from standardphysics_pipeline.measure import PipelineMeasurements
from standardphysics_pipeline.occupancy import build_grid
from standardphysics_pipeline.routes import clearance_map, room_clearance, widest_path

SHOPS = {"fixture": (build_graph, build_scenario), "lawsuit": (build_lawsuit_graph, build_lawsuit_scenario)}


def _legs(graph, scenario):
    grid = build_grid(graph)
    clearance = clearance_map(grid)
    for start, goal in zip(scenario.stops, scenario.stops[1:], strict=False):
        cells = grid.to_cell(start.position.x, start.position.y), grid.to_cell(goal.position.x, goal.position.y)
        yield grid, clearance, widest_path(grid, clearance, *cells, anchors=(start.anchor_node_id, goal.anchor_node_id))


@pytest.mark.parametrize("shop", SHOPS)
def test_every_leg_in_the_room_reads_its_widths_from_the_room_clearance(shop):
    build, route = SHOPS[shop]
    for grid, clearance, leg in _legs(build(), route()):
        assert leg.reachable
        assert np.array_equal(leg.clearance, room_clearance(grid, clearance))


def test_the_room_clearance_is_zero_wherever_a_trip_in_the_room_cannot_stand():
    grid = build_grid(build_lawsuit_graph())
    room = room_clearance(grid, clearance_map(grid))
    walkable = ~grid.occupied & grid.indoors
    assert (room[~walkable] == 0).all()
    assert (room[walkable] > 0).all()


def test_the_room_clearance_ends_at_the_doorway_where_the_ground_outside_begins():
    graph = build_lawsuit_graph()
    grid = build_grid(graph)
    plain = clearance_map(grid)
    room = room_clearance(grid, plain)
    assert (room <= plain).all()
    door = next(node for node in graph.nodes if node.kind == "door").transform.position
    just_inside = grid.to_cell(door.x, door.y + 0.3)
    assert room[just_inside] < plain[just_inside]


def test_a_leg_from_the_street_gets_the_ground_outside_and_measures_wider_by_the_door():
    grid, clearance, leg = next(_legs(build_graph(), build_street_scenario()))
    room = room_clearance(grid, clearance)
    assert (leg.clearance >= room).all()
    assert (leg.clearance > room).any()


def test_the_measurements_give_the_map_the_widths_their_routes_report():
    graph, scenario = build_lawsuit_graph(), build_lawsuit_scenario()
    measure = PipelineMeasurements()
    grid, room = measure.room_clearance(graph)
    for leg in range(len(scenario.stops) - 1):
        points = measure.route_clear_width(graph, scenario, leg).path
        widths = measure.route_path_clearances(graph, scenario, leg)
        measured = [(point, inches) for point, inches in zip(points, widths, strict=True) if inches is not None]
        assert measured
        for point, inches in measured:
            assert to_inches(float(room[grid.to_cell(point.x, point.y)]) * 2) == inches
