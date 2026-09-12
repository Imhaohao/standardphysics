"""How wide is the tightest point on the way from here to there.

The widest path problem, not the shortest. A customer does not care how far
they travel, they care whether they fit, so we maximise the narrowest point
along the route rather than minimising its length.

`scipy.ndimage.distance_transform_edt` gives every free cell its distance to
the nearest obstacle. A bottleneck Dijkstra over that field finds the path
whose minimum clearance is as large as possible. Twice that minimum is the
corridor width, and the cell where it occurs is the pinch the camera flies to.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from uuid import UUID

import numpy as np
from scipy import ndimage

from standardphysics_contracts import Vec3, to_inches, to_meters

from .occupancy import Grid

NEIGHBOURS = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]

MAX_EXEMPT_SHARE = 0.35
"""Most of a leg has to remain measurable.

A fixed exemption swallows a short leg whole. Counter to Pickup is 1.6 m, and
two 0.75 m circles leave a 0.1 m sliver pressed against the counter, so the
reported width describes that sliver rather than the route. The exemption
shrinks on short legs so there is always something real left to measure."""

ENDPOINT_EXEMPTION = 0.75
"""Metres around each stop that do not count toward the route's bottleneck.

Standing at a counter puts you within arm's reach of it, so the tightest point
of a journey is always its destination. That is not what a route width check
asks about. Whether there is room to sit at the counter is a separate question
with its own rule, so the approach to each stop is exempt here and measured by
`counter_approach` instead.
"""


@dataclass
class PathResult:
    clearance_radius: float
    """Metres from the path's tightest point to the nearest obstacle."""

    pinch_cell: tuple[int, int] | None
    path: list[tuple[int, int]]
    reachable: bool
    exempt: np.ndarray | None = None
    """Which cells were left out of the measurement.

    Inside the exemption the search has no preference between neighbours, so
    the route wanders and its clearance there describes nothing. Anything
    reading per-point values needs to know which ones to ignore."""

    @property
    def width_meters(self) -> float:
        return self.clearance_radius * 2


def clearance_map(grid: Grid) -> np.ndarray:
    """Metres from each free cell to the nearest obstacle."""
    return ndimage.distance_transform_edt(~grid.occupied) * grid.cell_size


def _nearest_free(grid: Grid, clearance: np.ndarray, cell: tuple[int, int]):
    """Snap a stop that landed inside furniture out to open floor."""
    row, col = cell
    if grid.contains(row, col) and not grid.occupied[row, col]:
        return row, col
    free = np.argwhere(~grid.occupied)
    if free.size == 0:
        return None
    distances = np.abs(free[:, 0] - row) + np.abs(free[:, 1] - col)
    nearest = free[int(np.argmin(distances))]
    return int(nearest[0]), int(nearest[1])


def _exempt_mask(
    grid: Grid, stops: list[tuple[int, int]], radius_m: float
) -> np.ndarray:
    rows, cols = grid.shape
    row_index, col_index = np.ogrid[:rows, :cols]
    mask = np.zeros((rows, cols), dtype=bool)
    radius_cells = radius_m / grid.cell_size
    for row, col in stops:
        mask |= ((row_index - row) ** 2 + (col_index - col) ** 2) <= radius_cells**2
    return mask


def _exemption_radius(
    grid: Grid, start: tuple[int, int], goal: tuple[int, int], requested: float
) -> float:
    separation = math.dist(start, goal) * grid.cell_size
    return min(requested, separation * MAX_EXEMPT_SHARE)


def widest_path(
    grid: Grid,
    clearance: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
    endpoint_exemption: float = ENDPOINT_EXEMPTION,
    extra_exempt: np.ndarray | None = None,
) -> PathResult:
    """Bottleneck Dijkstra: maximise the smallest clearance along the route."""
    start = _nearest_free(grid, clearance, start)
    goal = _nearest_free(grid, clearance, goal)
    if start is None or goal is None:
        return PathResult(0.0, None, [], reachable=False)

    radius = _exemption_radius(grid, start, goal, endpoint_exemption)
    exempt = _exempt_mask(grid, [start, goal], radius)
    if extra_exempt is not None:
        exempt |= extra_exempt
    search_field = np.where(exempt, np.inf, clearance)

    rows, cols = grid.shape
    best = np.full((rows, cols), -1.0)
    came_from: dict[tuple[int, int], tuple[int, int]] = {}

    best[start] = search_field[start]
    queue = [(-best[start], start)]

    while queue:
        negative_width, cell = heapq.heappop(queue)
        width = -negative_width
        if width < best[cell]:
            continue
        if cell == goal:
            break
        row, col = cell
        for d_row, d_col in NEIGHBOURS:
            neighbour = (row + d_row, col + d_col)
            if not grid.contains(*neighbour) or grid.occupied[neighbour]:
                continue
            candidate = min(width, search_field[neighbour])
            if candidate > best[neighbour]:
                best[neighbour] = candidate
                came_from[neighbour] = cell
                heapq.heappush(queue, (-candidate, neighbour))

    if best[goal] < 0:
        return PathResult(0.0, None, [], reachable=False)

    path = _retrace(came_from, start, goal)
    measured = [cell for cell in path if not exempt[cell]]
    if not measured:
        measured = path
    pinch = min(measured, key=lambda cell: clearance[cell])
    return PathResult(
        float(clearance[pinch]), pinch, path, reachable=True, exempt=exempt
    )


def _retrace(came_from, start, goal) -> list[tuple[int, int]]:
    path = [goal]
    while path[-1] != start:
        path.append(came_from[path[-1]])
    path.reverse()
    return path


def blockers_at(grid: Grid, cell: tuple[int, int], radius_cells: int) -> list[UUID]:
    """The distinct objects forming the pinch, nearest first.

    A finding names the two things the customer has to squeeze between, so this
    looks outward from the pinch and reports who it runs into.
    """
    row, col = cell
    rows, cols = grid.shape
    reach = max(radius_cells + 2, 3)
    row0, row1 = max(row - reach, 0), min(row + reach + 1, rows)
    col0, col1 = max(col - reach, 0), min(col + reach + 1, cols)

    window_owner = grid.owner[row0:row1, col0:col1]
    hits = np.argwhere(window_owner >= 0)
    if hits.size == 0:
        return []

    distances = (hits[:, 0] + row0 - row) ** 2 + (hits[:, 1] + col0 - col) ** 2
    ordered = hits[np.argsort(distances)]

    found: list[UUID] = []
    for hit_row, hit_col in ordered:
        node_id = grid.node_ids[int(window_owner[hit_row, hit_col])]
        if node_id not in found:
            found.append(node_id)
        if len(found) == 2:
            break
    return found


def sample_cells(cells: list[tuple[int, int]], step: int = 3) -> list[tuple[int, int]]:
    """Which cells become drawable points. One definition, so a path and its
    per-point clearances cannot drift out of step with each other."""
    if not cells:
        return []
    sampled = cells[::step]
    if sampled[-1] != cells[-1]:
        sampled.append(cells[-1])
    return sampled


def path_clearances(
    grid: Grid,
    clearance: np.ndarray,
    cells: list[tuple[int, int]],
    step: int = 3,
    exempt: np.ndarray | None = None,
) -> list[float | None]:
    """Corridor width in inches at each drawn point, for colouring a route.

    `None` where the point falls inside the endpoint exemption. The route
    wanders there because every cell looks equally good to the search, so a
    number would be a measurement of nothing. A viewer should leave those
    stretches uncoloured rather than paint them as tight.
    """
    return [
        None
        if exempt is not None and exempt[cell]
        else to_inches(float(clearance[cell]) * 2)
        for cell in sample_cells(cells, step)
    ]


def world_path(grid: Grid, cells: list[tuple[int, int]], step: int = 3) -> list[Vec3]:
    """Thin the cell path down to something a viewer can draw.

    Kept dense enough that turn detection can still see a bend: at 25 mm cells
    every third sample is 75 mm, so a 180 around a narrow pivot survives.
    """
    return [grid.to_world(row, col) for row, col in sample_cells(cells, step)]


def longest_run_below(
    grid: Grid,
    clearance: np.ndarray,
    cells: list[tuple[int, int]],
    threshold_inches: float,
) -> float:
    """The longest unbroken stretch of a route narrower than `threshold_inches`.

    ADA 2010 403.5.1 permits a route to narrow to 32 inches, but only for a run
    of 24 inches at most. A bottleneck says how tight the route gets and says
    nothing about how long it stays that way, so the exception cannot be
    settled without this.

    The threshold is an argument rather than a constant because it belongs to
    the rule pack, where a person has checked it against the source.
    """
    longest = 0.0
    current = 0.0
    previous = None
    limit = to_meters(threshold_inches) / 2

    for cell in cells:
        below = clearance[cell] < limit
        if below and previous is not None:
            current += math.dist(previous, cell) * grid.cell_size
        elif below:
            current = 0.0
        else:
            longest = max(longest, current)
            current = 0.0
        previous = cell if below else None

    return to_inches(max(longest, current))
