"""The clearance map of a layout: how much room there is around every point of its floor.

It is read off the grid the route checks measure on, for the same base revision and moves a drag check is asked
about, so the colours under the plan and the findings beside it come from one measurement and cannot disagree.
"""

from __future__ import annotations

import base64
import io
import uuid

import numpy as np
from PIL import Image
from standardphysics_agents import Observation, finding_id, load_pack
from standardphysics_agents.checks.route_width import RULE_ID as ROUTE_WIDTH
from standardphysics_agents.checks.turning_space import RULE_ID as TURNING_SPACE
from standardphysics_agents.rules.pack import COMPARISON_EPSILON
from standardphysics_agents.tracing import suspend_tracing
from standardphysics_contracts import (
    ClearanceBands,
    ClearanceMap,
    ClearancePinch,
    LayoutCheckRequest,
    Vec3,
    graph_hash,
    to_meters,
)

from .db import Database
from .layout import _base, plan_candidate
from .stages import Stages

WIDTH_STEP_INCHES = 0.5
"""Inches per stored step. Half the inch the grid resolves, and 254 steps reach past ten feet."""

NO_FLOOR = 0
WIDEST = 255


def clearance_map(database: Database, stages: Stages, scan_id: uuid.UUID, body: LayoutCheckRequest) -> ClearanceMap:
    """The map of the layout a drag check of `body` measures: the same base, the same moves, the same grid.

    Tracing is suspended because a map is a view of measurements the drag check already traces, and tracing one
    takes a check from a third of a second to several.
    """
    base, _, scenario = _base(database, scan_id, body.base_revision)
    candidate, _ = plan_candidate(base, body.moves, construction=True)
    with suspend_tracing():
        measured = stages.clearance(candidate, scenario)
    grid = measured.grid
    return ClearanceMap(
        sequence=body.sequence,
        graph_hash=graph_hash(candidate),
        origin=Vec3(x=grid.origin_x, y=grid.origin_y, z=0.0),
        cell_meters=grid.cell_size,
        columns=grid.shape[1],
        rows=grid.shape[0],
        rotation_z_degrees=0.0,
        widths_png=widths_png(measured.metres),
        width_step_inches=WIDTH_STEP_INCHES,
        bands=bands(),
        pinches=[pinch for observation in measured.pinches if (pinch := _pinch(observation, candidate.scan_id))],
    )


def width_codes(metres: np.ndarray) -> np.ndarray:
    """Each cell's clear width in whole steps, rounded down, with `NO_FLOOR` where nobody can stand.

    The epsilon is the one rule comparisons allow, so a width a check takes as meeting a threshold is stored at or
    above it rather than a step below.
    """
    inches = metres * 2.0 / to_meters(1.0)
    steps = np.floor((inches + COMPARISON_EPSILON) / WIDTH_STEP_INCHES)
    return np.where(metres > 0, np.clip(steps, 1, WIDEST), NO_FLOOR).astype(np.uint8)


def widths_png(metres: np.ndarray) -> str:
    """The width codes as a grey PNG, base64, its first row the grid's highest y so it reads as a plan."""
    buffer = io.BytesIO()
    Image.fromarray(width_codes(metres)[::-1]).save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def bands() -> ClearanceBands:
    """Where the map changes colour, from the rule pack the checks read, so a band edge is a rule's own number."""
    pack = load_pack()
    route = pack.by_id(ROUTE_WIDTH)
    return ClearanceBands(
        reduced_inches=route.parameter("reduced_min_inches"),
        route_inches=route.threshold,
        reduced_run_inches=route.parameter("reduced_max_run_inches"),
        turning_inches=pack.by_id(TURNING_SPACE).threshold,
    )


def _pinch(observation: Observation, scan_id: uuid.UUID) -> ClearancePinch | None:
    if observation.locus is None:
        return None
    return ClearancePinch(
        finding_id=finding_id(scan_id, observation),
        point=observation.locus.point,
        inches=observation.measured_inches,
        meets_rule=observation.satisfied,
        origin=observation.facts["origin"],
        destination=observation.facts["destination"],
        blocking_node_ids=list(observation.relied_on),
    )
