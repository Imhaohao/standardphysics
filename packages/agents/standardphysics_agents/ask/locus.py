"""Pointing the viewer at whatever a question was about.

An answer with no place to look is a fact in a list. An answer that flies the
camera to the four tables while it tells you about them is the shop talking
back, which is the point of the thing.
"""

from __future__ import annotations

from standardphysics_contracts import Annotation, Locus, SceneNode, Vec3
from standardphysics_pipeline import footprint
from standardphysics_pipeline.locus import camera_for

PADDING = 0.5

MIN_FRAME_RADIUS = 0.8


def _extent(nodes: list[SceneNode]) -> tuple[Vec3, Vec3]:
    corners = [point for node in nodes for point in footprint(node)]
    tops = [node.transform.position.z + node.dimensions.z / 2 for node in nodes]
    return (
        Vec3(x=min(x for x, _ in corners), y=min(y for _, y in corners), z=0.0),
        Vec3(
            x=max(x for x, _ in corners),
            y=max(y for _, y in corners),
            z=max(tops, default=0.0),
        ),
    )


def subject_locus(nodes: list[SceneNode], label: str) -> Locus | None:
    """A patch of floor covering everything the question was about."""
    if not nodes:
        return None
    low, high = _extent(nodes)
    centre = Vec3(x=(low.x + high.x) / 2, y=(low.y + high.y) / 2, z=0.0)
    corners = [
        Vec3(x=low.x - PADDING, y=low.y - PADDING, z=0.02),
        Vec3(x=high.x + PADDING, y=low.y - PADDING, z=0.02),
        Vec3(x=high.x + PADDING, y=high.y + PADDING, z=0.02),
        Vec3(x=low.x - PADDING, y=high.y + PADDING, z=0.02),
    ]
    radius = max((high.x - low.x) / 2, (high.y - low.y) / 2, MIN_FRAME_RADIUS)
    return Locus(
        point=centre,
        bbox_min=Vec3(x=low.x - PADDING, y=low.y - PADDING, z=0.0),
        bbox_max=Vec3(x=high.x + PADDING, y=high.y + PADDING, z=high.z + PADDING),
        node_ids=[node.id for node in nodes],
        annotation=Annotation(kind="region", points=corners, label=label),
        camera=camera_for(centre, radius, (0.0, -1.0), fov_degrees=55.0),
    )
