"""A dimension line up the front of something, for the height checks.

Lane B's locus module draws across a gap and around a floor patch. A counter
height is a vertical measurement, so this builds that one shape from the same
camera helper rather than inventing a second way to frame a subject. Asked for
in docs/handoffs/C-to-B.md; it belongs beside the other two.
"""

from __future__ import annotations

from standardphysics_contracts import (
    Annotation,
    HeightResult,
    Locus,
    SceneNode,
    Vec3,
    to_inches,
    to_meters,
)
from standardphysics_pipeline import format_inches
from standardphysics_pipeline.locus import camera_for

FRAME_PADDING = 0.5


def _front_face(node: SceneNode, at: Vec3) -> tuple[Vec3, tuple[float, float]]:
    """The middle of the long face, and which way to look at it from.

    A counter is wide and shallow, so its short axis faces the customer.
    """
    centre = node.transform.position
    facing_y = node.dimensions.x >= node.dimensions.y
    offset = (node.dimensions.y if facing_y else node.dimensions.x) / 2
    direction = (0.0, -1.0) if facing_y else (-1.0, 0.0)
    return (
        Vec3(
            x=at.x + direction[0] * offset,
            y=centre.y + direction[1] * offset if facing_y else at.y,
            z=0.0,
        ),
        direction,
    )


def height_locus(node: SceneNode, result: HeightResult) -> Locus:
    base, direction = _front_face(node, result.measured_at)
    top = Vec3(x=base.x, y=base.y, z=to_meters(result.inches))
    return Locus(
        point=top,
        bbox_min=Vec3(x=base.x - FRAME_PADDING, y=base.y - FRAME_PADDING, z=0.0),
        bbox_max=Vec3(
            x=base.x + FRAME_PADDING,
            y=base.y + FRAME_PADDING,
            z=top.z + FRAME_PADDING,
        ),
        node_ids=[node.id],
        annotation=Annotation(
            kind="dimension_line",
            points=[base, top],
            label=format_inches(result.inches),
        ),
        camera=camera_for(
            Vec3(x=base.x, y=base.y, z=top.z / 2), max(top.z, 1.0), direction
        ),
    )


def mounted_locus(node: SceneNode) -> Locus:
    """A patch around one piece, for a finding about the piece itself."""
    centre = node.transform.position
    reach = max(node.dimensions.x, node.dimensions.y) / 2 + FRAME_PADDING
    corners = [
        Vec3(x=centre.x - reach, y=centre.y - reach, z=0.02),
        Vec3(x=centre.x + reach, y=centre.y - reach, z=0.02),
        Vec3(x=centre.x + reach, y=centre.y + reach, z=0.02),
        Vec3(x=centre.x - reach, y=centre.y + reach, z=0.02),
    ]
    top = centre.z + node.dimensions.z / 2
    return Locus(
        point=Vec3(x=centre.x, y=centre.y, z=top),
        bbox_min=Vec3(x=centre.x - reach, y=centre.y - reach, z=0.0),
        bbox_max=Vec3(x=centre.x + reach, y=centre.y + reach, z=top + FRAME_PADDING),
        node_ids=[node.id],
        annotation=Annotation(
            kind="region", points=corners, label=format_inches(to_inches(top))
        ),
        camera=camera_for(
            Vec3(x=centre.x, y=centre.y, z=top / 2), max(reach, 1.0), (0.0, -1.0)
        ),
    )
