"""The MeasurementProvider Lane C calls.

Grid for topology, geometry for the number. The occupancy grid finds the route
and names what pinches it; the width we report is the exact distance between
those two footprints, because 25 mm cells carry about an inch of error and a
threshold check cannot afford that.
"""

from __future__ import annotations

from uuid import UUID

import numpy as np

from standardphysics_contracts import (
    ClearFloorResult,
    HeightResult,
    Scenario,
    SceneGraph,
    SceneNode,
    Vec3,
    WidthResult,
    to_inches,
    to_meters,
)

from .footprints import (
    Polygon,
    footprint,
    gap_between,
    gap_between_nodes,
    rotation_about_z,
)
from .occupancy import CELL_SIZE, Grid, blocks_floor, build_grid
from .routes import blockers_at, clearance_map, widest_path, world_path
from .turns import Turn, measure_turn  # noqa: F401  (Turn is part of the API)

COUNTER_CLEAR_WIDTH = to_meters(48.0)
COUNTER_CLEAR_DEPTH = to_meters(30.0)
"""ADA 2010 305.3 clear floor space, laid out for a parallel approach with the
48 in side running along the counter."""


def _signature(graph: SceneGraph) -> tuple:
    """Everything the grid depends on, so moving, turning or resizing any node
    rebuilds it, and asking three questions about one layout does not."""
    return tuple(
        (str(node.id), node.kind, tuple(node.transform.m), node.dimensions.as_tuple())
        for node in graph.nodes
    )


def _rectangle(
    centre: Vec3, width: float, depth: float, cos_t: float, sin_t: float
) -> Polygon:
    """A width by depth rectangle turned to match the object it sits against."""
    half_w, half_d = width / 2, depth / 2
    corners = [(-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d)]
    return [
        (centre.x + x * cos_t - y * sin_t, centre.y + x * sin_t + y * cos_t)
        for x, y in corners
    ]


class PipelineMeasurements:
    """Implements MeasurementProvider against real geometry."""

    def __init__(self, cell_size: float = CELL_SIZE) -> None:
        self.cell_size = cell_size
        self._cache: dict[tuple, tuple[Grid, np.ndarray]] = {}

    def _field(self, graph: SceneGraph) -> tuple[Grid, np.ndarray]:
        key = _signature(graph)
        if key not in self._cache:
            grid = build_grid(graph, self.cell_size)
            self._cache = {key: (grid, clearance_map(grid))}
        return self._cache[key]

    def route_clear_width(
        self, graph: SceneGraph, scenario: Scenario, leg_index: int
    ) -> WidthResult:
        grid, clearance = self._field(graph)
        start = scenario.stops[leg_index].position
        goal = scenario.stops[leg_index + 1].position

        result = widest_path(
            grid,
            clearance,
            grid.to_cell(start.x, start.y),
            grid.to_cell(goal.x, goal.y),
        )
        if not result.reachable or result.pinch_cell is None:
            return WidthResult(
                inches=0.0, pinch_point=goal, blocking_node_ids=[], reachable=False
            )

        radius_cells = int(result.clearance_radius / grid.cell_size)
        blockers = blockers_at(grid, result.pinch_cell, radius_cells)
        return WidthResult(
            inches=self._exact_width(graph, blockers, result.width_meters),
            pinch_point=grid.to_world(*result.pinch_cell),
            blocking_node_ids=blockers,
            path=world_path(grid, result.path),
            reachable=True,
        )

    def _exact_width(
        self, graph: SceneGraph, blockers: list[UUID], grid_width: float
    ) -> float:
        """Two named obstacles measure exactly. Anything else keeps the grid's
        answer, which is good to about an inch."""
        if len(blockers) != 2:
            return to_inches(grid_width)
        a, b = (graph.by_id(node_id) for node_id in blockers)
        return to_inches(gap_between_nodes(a, b))

    def turn_clear_width(
        self, graph: SceneGraph, scenario: Scenario, leg_index: int
    ) -> WidthResult:
        """The binding width for ADA 2010 403.5.2, where the rule applies.

        A 180 degree turn has three requirements, not one, so this reports the
        zone with the worst shortfall against its own threshold. Call
        `turn_detail` for all three numbers and the pivot.

        When the leg has no 180 degree turn the rule does not apply, and this
        returns the plain route width so a caller that ignores applicability
        still gets a true number rather than a zero.
        """
        turn = self.turn_detail(graph, scenario, leg_index)
        if turn is None:
            return self.route_clear_width(graph, scenario, leg_index)

        measured, _ = turn.binding_measurement
        return WidthResult(
            inches=measured,
            pinch_point=turn.apex,
            blocking_node_ids=[turn.pivot_id] if turn.pivot_id else [],
            path=self.route_clear_width(graph, scenario, leg_index).path,
            reachable=True,
        )

    def turn_detail(
        self, graph: SceneGraph, scenario: Scenario, leg_index: int
    ) -> Turn | None:
        """All three widths and the element being turned around, or None when
        the leg runs through without doubling back."""
        grid, clearance = self._field(graph)
        route = self.route_clear_width(graph, scenario, leg_index)
        if not route.reachable or not route.path:
            return None
        return measure_turn(graph, grid, clearance, route.path)

    def turning_space(self, graph: SceneGraph, at: Vec3) -> ClearFloorResult:
        _, clearance = self._field(graph)
        grid, _ = self._field(graph)
        row, col = grid.to_cell(at.x, at.y)
        if not grid.contains(row, col):
            return ClearFloorResult(
                inches_wide=0.0, inches_deep=0.0, center=at, fits=False
            )
        diameter = to_inches(float(clearance[row, col]) * 2)
        return ClearFloorResult(
            inches_wide=diameter,
            inches_deep=diameter,
            center=at,
            fits=diameter >= 60.0,
        )

    def door_clear_width(self, graph: SceneGraph, door_id: UUID) -> WidthResult:
        door = graph.by_id(door_id)
        opening = max(door.dimensions.x, door.dimensions.y)
        return WidthResult(
            inches=to_inches(opening),
            pinch_point=door.transform.position,
            blocking_node_ids=[door_id],
        )

    def counter_height(self, graph: SceneGraph, counter_id: UUID) -> HeightResult:
        counter = graph.by_id(counter_id)
        top = counter.transform.position.z + counter.dimensions.z / 2
        return HeightResult(
            inches=to_inches(top),
            node_id=counter_id,
            measured_at=counter.transform.position,
        )

    def counter_approach(
        self, graph: SceneGraph, counter_id: UUID
    ) -> ClearFloorResult:
        counter = graph.by_id(counter_id)
        centre = self._approach_centre(counter)
        space = _rectangle(
            centre, COUNTER_CLEAR_WIDTH, COUNTER_CLEAR_DEPTH, *rotation_about_z(counter)
        )
        intruders = self._intruders(graph, counter_id, space)
        return ClearFloorResult(
            inches_wide=to_inches(COUNTER_CLEAR_WIDTH),
            inches_deep=to_inches(COUNTER_CLEAR_DEPTH),
            center=centre,
            fits=not intruders,
        )

    def _approach_centre(self, counter: SceneNode) -> Vec3:
        """In front of the counter's local minus-Y face, turned with the counter."""
        position = counter.transform.position
        cos_t, sin_t = rotation_about_z(counter)
        offset = counter.dimensions.y / 2 + COUNTER_CLEAR_DEPTH / 2
        return Vec3(x=position.x + offset * sin_t, y=position.y - offset * cos_t, z=0.0)

    def _intruders(
        self, graph: SceneGraph, counter_id: UUID, space: Polygon
    ) -> list[UUID]:
        found = []
        for node in graph.nodes:
            if node.id == counter_id or not blocks_floor(node):
                continue
            if gap_between(footprint(node), space) == 0.0:
                found.append(node.id)
        return found
