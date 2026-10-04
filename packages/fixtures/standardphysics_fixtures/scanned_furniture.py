"""Furniture as a LiDAR scan shows it, built from boxes, for testing what lies under a table.

A phone scan sees a table as its top, its legs and the floor around and under
it, as far as the camera reached; RoomPlan boxes the same table as one block
from the floor to the top. These build both: a `SceneNode` for the box, and the
triangles the mesh would hold, in the room frame with Z up. A test can then say
exactly which floor was seen and what stands under the top.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from standardphysics_contracts import LidarMesh, Mat4, SceneNode, Vec3

from .shop import node_id

FLOOR_TILE = 0.05
"""Metres across each square of floor the mesh saw."""

Point = tuple[float, float, float]
Rectangle = tuple[float, float, float, float]
"""x0, y0, x1, y1 in the room frame."""


@dataclass
class MeshSketch:
    """Triangles gathered into a single LiDAR mesh part, already in the room frame."""

    vertices: list[float] = field(default_factory=list)
    triangles: list[int] = field(default_factory=list)

    def box(self, low: Point, high: Point) -> MeshSketch:
        """All six faces of an axis-aligned box."""
        (x0, y0, z0), (x1, y1, z1) = low, high
        corners = (
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        )
        sides = ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
        return self._quads(corners, sides)

    def floor(self, area: Rectangle, unseen: tuple[Rectangle, ...] = ()) -> MeshSketch:
        """Floor tiles lying at z = 0 across `area`, leaving out every tile whose middle is in an `unseen` rectangle."""
        x0, y0, x1, y1 = area
        for i in range(round((x1 - x0) / FLOOR_TILE)):
            for j in range(round((y1 - y0) / FLOOR_TILE)):
                x, y = x0 + i * FLOOR_TILE, y0 + j * FLOOR_TILE
                if not any(_holds(hole, x + FLOOR_TILE / 2, y + FLOOR_TILE / 2) for hole in unseen):
                    tile = ((x, y, 0.0), (x + FLOOR_TILE, y, 0.0), (x + FLOOR_TILE, y + FLOOR_TILE, 0.0), (x, y + FLOOR_TILE, 0.0))
                    self._quads(tile, ((0, 1, 2, 3),))
        return self

    def mesh(self) -> LidarMesh:
        part = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"sketch-{len(self.vertices)}")),
            "transform": Mat4.identity().m,
            "vertices": self.vertices,
            "triangles": self.triangles,
        }
        return LidarMesh.model_validate({"parts": [part]})

    def _quads(self, corners, quads) -> MeshSketch:
        base = len(self.vertices) // 3
        for corner in corners:
            self.vertices += [float(value) for value in corner]
        for a, b, c, d in quads:
            self.triangles += [base + a, base + b, base + c, base + a, base + c, base + d]
        return self


def _holds(rectangle: Rectangle, x: float, y: float) -> bool:
    x0, y0, x1, y1 = rectangle
    return x0 <= x <= x1 and y0 <= y <= y1


@dataclass(frozen=True)
class ScannedTable:
    """A table: a top `thickness` deep whose surface stands `height` up, on square legs at its corners.

    `width` runs along the room's x and `depth` along its y. `legs_apart`
    narrows the legs along x toward the middle, so the opening between them
    can be set to any width.
    """

    name: str
    centre: tuple[float, float]
    width: float
    depth: float
    height: float
    thickness: float = 0.03
    leg: float = 0.04
    legs_apart: float | None = None

    @property
    def footprint(self) -> Rectangle:
        x, y = self.centre
        return x - self.width / 2, y - self.depth / 2, x + self.width / 2, y + self.depth / 2

    @property
    def underside(self) -> float:
        return self.height - self.thickness

    def node(self, movable: bool = True, raw_category: str = "table") -> SceneNode:
        return SceneNode(
            id=node_id(self.name),
            kind="object",
            label=self.name,
            raw_category=raw_category,
            dimensions=Vec3(x=self.width, y=self.depth, z=self.height),
            transform=Mat4.translation(self.centre[0], self.centre[1], self.height / 2),
            movable=movable,
        )

    def drawn(self, sketch: MeshSketch) -> MeshSketch:
        """The top and the legs, added to `sketch`."""
        x0, y0, x1, y1 = self.footprint
        sketch.box((x0, y0, self.underside), (x1, y1, self.height))
        for leg_x in self._leg_columns():
            for leg_y in (y0, y1 - self.leg):
                sketch.box((leg_x, leg_y, 0.0), (leg_x + self.leg, leg_y + self.leg, self.underside))
        return sketch

    def _leg_columns(self) -> tuple[float, float]:
        if self.legs_apart is None:
            x0, _, x1, _ = self.footprint
            return x0, x1 - self.leg
        middle = self.centre[0]
        return middle - self.legs_apart / 2 - self.leg, middle + self.legs_apart / 2
