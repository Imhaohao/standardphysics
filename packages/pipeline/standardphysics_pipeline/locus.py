"""Turning a measurement into something the viewer can fly to and draw.

A number on its own does not help anyone. `31 in` matters when the camera is
looking at the actual gap, the two objects causing it are lit up, and the
measurement is drawn across the space it describes. This builds that.

Lane C attaches a `Locus` to each finding. Lane D's viewer reads `camera` to
tween, `node_ids` to highlight, and `annotation` to draw.
"""

from __future__ import annotations

import math

from standardphysics_contracts import (
    Annotation,
    CameraPose,
    ClearFloorResult,
    Locus,
    SceneGraph,
    Vec3,
    WidthResult,
    to_meters,
)

from .footprints import closest_points, footprint

EYE_PITCH_DEGREES = 38.0
"""Looking down at a floor gap reads better than standing level with it."""

FRAMING_MARGIN = 1.45
"""Leaves air around the subject so the dimension label is not against an edge."""

MIN_CAMERA_DISTANCE = 1.2
MIN_EYE_HEIGHT = 1.1


def format_inches(value: float) -> str:
    """`31 in`, not `31.000000 in` and not `0.7874 m`."""
    rounded = round(value)
    if abs(value - rounded) < 0.05:
        return f"{rounded} in"
    return f"{value:.1f} in"


def _midpoint(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(x=(a.x + b.x) / 2, y=(a.y + b.y) / 2, z=(a.z + b.z) / 2)


def _perpendicular(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    if length == 0:
        return 1.0, 0.0
    return -dy / length, dx / length


def _viewing_side(
    subject: Vec3, across: tuple[float, float], approach: Vec3 | None
) -> tuple[float, float]:
    """Look from where the customer comes from, when we know."""
    if approach is None:
        return across
    toward = (approach.x - subject.x, approach.y - subject.y)
    if toward[0] * across[0] + toward[1] * across[1] < 0:
        return (-across[0], -across[1])
    return across


def camera_for(
    subject: Vec3,
    radius: float,
    view_direction: tuple[float, float],
    fov_degrees: float = 50.0,
) -> CameraPose:
    """Frame a sphere of `radius` around `subject` from the given direction."""
    half_fov = math.radians(fov_degrees) / 2
    distance = max(radius * FRAMING_MARGIN / math.tan(half_fov), MIN_CAMERA_DISTANCE)
    pitch = math.radians(EYE_PITCH_DEGREES)

    ground = distance * math.cos(pitch)
    height = max(distance * math.sin(pitch), MIN_EYE_HEIGHT)
    return CameraPose(
        position=Vec3(
            x=subject.x + view_direction[0] * ground,
            y=subject.y + view_direction[1] * ground,
            z=subject.z + height,
        ),
        target=subject,
        fov_degrees=fov_degrees,
    )


def _bbox(points: list[Vec3], padding: float) -> tuple[Vec3, Vec3]:
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    return (
        Vec3(x=min(xs) - padding, y=min(ys) - padding, z=min(zs)),
        Vec3(x=max(xs) + padding, y=max(ys) + padding, z=max(zs) + padding),
    )


def width_locus(
    graph: SceneGraph, result: WidthResult, draw_height: float = 0.05
) -> Locus:
    """A dimension line drawn across the actual gap, seen from the approach."""
    endpoints = _measurement_endpoints(graph, result, draw_height)
    start, end = endpoints
    subject = _midpoint(start, end)

    across = _perpendicular(end.x - start.x, end.y - start.y)
    approach = result.path[0] if result.path else None
    direction = _viewing_side(subject, across, approach)

    span = math.dist((start.x, start.y), (end.x, end.y))
    radius = max(span, 1.0)

    return Locus(
        point=result.pinch_point,
        bbox_min=_bbox([start, end], padding=0.6)[0],
        bbox_max=_bbox([start, end], padding=0.6)[1],
        node_ids=list(result.blocking_node_ids),
        annotation=Annotation(
            kind="dimension_line",
            points=[start, end],
            label=format_inches(result.inches),
        ),
        camera=camera_for(subject, radius, direction),
    )


def _measurement_endpoints(
    graph: SceneGraph, result: WidthResult, draw_height: float
) -> tuple[Vec3, Vec3]:
    """Where the dimension line actually attaches.

    With two named blockers the line runs between their facing surfaces. With
    anything else the best we can honestly draw is a span centred on the pinch.
    """
    if len(result.blocking_node_ids) == 2:
        a, b = (graph.by_id(node_id) for node_id in result.blocking_node_ids)
        point_a, point_b = closest_points(footprint(a), footprint(b))
        return (
            Vec3(x=point_a[0], y=point_a[1], z=draw_height),
            Vec3(x=point_b[0], y=point_b[1], z=draw_height),
        )

    half = to_meters(result.inches) / 2
    pinch = result.pinch_point
    return (
        Vec3(x=pinch.x - half, y=pinch.y, z=draw_height),
        Vec3(x=pinch.x + half, y=pinch.y, z=draw_height),
    )


def region_locus(
    result: ClearFloorResult, node_ids: list, draw_height: float = 0.02
) -> Locus:
    """A floor patch, for turning space and clear floor space checks."""
    half_w = to_meters(result.inches_wide) / 2
    half_d = to_meters(result.inches_deep) / 2
    centre = result.center
    corners = [
        Vec3(x=centre.x - half_w, y=centre.y - half_d, z=draw_height),
        Vec3(x=centre.x + half_w, y=centre.y - half_d, z=draw_height),
        Vec3(x=centre.x + half_w, y=centre.y + half_d, z=draw_height),
        Vec3(x=centre.x - half_w, y=centre.y + half_d, z=draw_height),
    ]
    bbox_min, bbox_max = _bbox(corners, padding=0.4)
    return Locus(
        point=centre,
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        node_ids=list(node_ids),
        annotation=Annotation(
            kind="region",
            points=corners,
            label=format_inches(min(result.inches_wide, result.inches_deep)),
        ),
        camera=camera_for(centre, max(half_w, half_d) * 2, (0.0, -1.0)),
    )


def path_locus(result: WidthResult, label: str | None = None) -> Locus:
    """The whole route, for before and after replay."""
    points = result.path or [result.pinch_point]
    bbox_min, bbox_max = _bbox(points, padding=0.5)
    centre = _midpoint(bbox_min, bbox_max)
    extent = max(bbox_max.x - bbox_min.x, bbox_max.y - bbox_min.y)
    return Locus(
        point=result.pinch_point,
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        node_ids=list(result.blocking_node_ids),
        annotation=Annotation(
            kind="path",
            points=points,
            label=label or format_inches(result.inches),
        ),
        camera=camera_for(centre, extent / 2, (0.0, -1.0), fov_degrees=60.0),
    )
