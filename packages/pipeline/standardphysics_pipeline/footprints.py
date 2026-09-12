"""Exact distances between the things people squeeze between.

The occupancy grid is how we find a route and identify what pinches it. It is
not how we report the number: at 25 mm cells the answer carries about an inch
of quantisation, which is enough to pass a 34 inch gap as 36.

So the grid finds the pinch and names the two objects, and the width we report
is the exact distance between those two footprints.
"""

from __future__ import annotations

import math

from standardphysics_contracts import SceneNode

Point = tuple[float, float]
Polygon = list[Point]


def footprint(node: SceneNode) -> Polygon:
    """The node's floor rectangle, rotated about Z, in world coordinates."""
    m = node.transform.m
    cos_t, sin_t = m[0], m[4]
    scale = math.hypot(cos_t, sin_t)
    if scale == 0:
        cos_t, sin_t = 1.0, 0.0
    else:
        cos_t, sin_t = cos_t / scale, sin_t / scale

    centre = node.transform.position
    half_x, half_y = node.dimensions.x / 2, node.dimensions.y / 2
    corners = [(-half_x, -half_y), (half_x, -half_y), (half_x, half_y), (-half_x, half_y)]
    return [
        (
            centre.x + local_x * cos_t - local_y * sin_t,
            centre.y + local_x * sin_t + local_y * cos_t,
        )
        for local_x, local_y in corners
    ]


def _point_to_segment(point: Point, a: Point, b: Point) -> float:
    px, py = point
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_squared))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _edges(polygon: Polygon):
    return zip(polygon, polygon[1:] + polygon[:1])


def _separated(a: Polygon, b: Polygon) -> bool:
    """Separating axis test over both rectangles' edge normals."""
    for polygon in (a, b):
        for start, end in _edges(polygon):
            axis = (-(end[1] - start[1]), end[0] - start[0])
            a_projected = [axis[0] * x + axis[1] * y for x, y in a]
            b_projected = [axis[0] * x + axis[1] * y for x, y in b]
            if max(a_projected) < min(b_projected) or max(b_projected) < min(a_projected):
                return True
    return False


def gap_between(a: Polygon, b: Polygon) -> float:
    """Shortest distance between two convex footprints. Zero if they touch."""
    if not _separated(a, b):
        return 0.0
    distances = []
    for point in a:
        distances += [_point_to_segment(point, s, e) for s, e in _edges(b)]
    for point in b:
        distances += [_point_to_segment(point, s, e) for s, e in _edges(a)]
    return min(distances)


def gap_between_nodes(a: SceneNode, b: SceneNode) -> float:
    return gap_between(footprint(a), footprint(b))


def _closest_on_segment(point: Point, a: Point, b: Point) -> Point:
    px, py = point
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return a
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_squared))
    return (ax + t * dx, ay + t * dy)


def closest_points(a: Polygon, b: Polygon) -> tuple[Point, Point]:
    """The two points a dimension line should run between.

    Measuring a gap is not enough to draw it. The label has to sit across the
    actual facing surfaces, so this returns where on each footprint the
    shortest distance is realised.
    """
    best = None
    for point in a:
        candidate = _closest_on_segment(point, *_nearest_edge(point, b))
        best = _better(best, point, candidate)
    for point in b:
        candidate = _closest_on_segment(point, *_nearest_edge(point, a))
        best = _better(best, candidate, point)
    return best[1], best[2]


def _nearest_edge(point: Point, polygon: Polygon) -> tuple[Point, Point]:
    return min(_edges(polygon), key=lambda edge: _point_to_segment(point, *edge))


def _better(best, first: Point, second: Point):
    distance = math.hypot(first[0] - second[0], first[1] - second[1])
    if best is None or distance < best[0]:
        return (distance, first, second)
    return best
