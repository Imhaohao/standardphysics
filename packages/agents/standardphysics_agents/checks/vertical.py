"""A patch around one piece, for a finding about the piece itself.

Lane B's `height_locus` draws the vertical dimension line. Protrusions and
dining surfaces still need a region around the object, which is this.
"""

from __future__ import annotations

from standardphysics_contracts import Annotation, Locus, SceneNode, Vec3, to_inches
from standardphysics_pipeline import format_inches
from standardphysics_pipeline.locus import camera_for

FRAME_PADDING = 0.5


def mounted_locus(node: SceneNode) -> Locus:
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
