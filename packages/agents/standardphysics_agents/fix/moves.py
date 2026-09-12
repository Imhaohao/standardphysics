"""Applying a proposal to a layout.

A move translates on the floor and turns about Z. Nothing here can change a
dimension, because there is no code path that writes one: the candidate node is
copied from the original with a new transform and nothing else.
"""

from __future__ import annotations

import math
from uuid import UUID

from standardphysics_contracts import Mat4, NodeMove, SceneGraph, SceneNode, Vec3
from standardphysics_pipeline import footprint
from standardphysics_pipeline.footprints import rotation_about_z


def _turned(node: SceneNode, degrees: float, position: Vec3) -> Mat4:
    """A transform holding the node's rotation about Z plus `degrees`.

    Furniture standing on a floor is a Z rotation and a translation, which is
    what RoomPlan reports and what a drag produces. A transform carrying
    anything else is not something a rearrangement should be composing with.
    """
    cos_t, sin_t = rotation_about_z(node)
    cos_d, sin_d = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    cos_new = cos_t * cos_d - sin_t * sin_d
    sin_new = sin_t * cos_d + cos_t * sin_d
    return Mat4(
        m=[
            cos_new, -sin_new, 0.0, position.x,
            sin_new, cos_new, 0.0, position.y,
            0.0, 0.0, 1.0, position.z,
            0.0, 0.0, 0.0, 1.0,
        ]
    )


def move_node(node: SceneNode, move: NodeMove) -> SceneNode:
    origin = node.transform.position
    moved_to = Vec3(
        x=origin.x + move.delta_translation.x,
        y=origin.y + move.delta_translation.y,
        z=origin.z + move.delta_translation.z,
    )
    return node.model_copy(
        update={"transform": _turned(node, move.delta_rotation_z_degrees, moved_to)}
    )


def apply_moves(graph: SceneGraph, moves: list[NodeMove]) -> SceneGraph:
    """A new layout. The original is never touched, so a rejected candidate
    cannot leave anything behind."""
    by_node: dict[UUID, NodeMove] = {move.node_id: move for move in moves}
    nodes = [
        move_node(node, by_node[node.id]) if node.id in by_node else node
        for node in graph.nodes
    ]
    return graph.model_copy(
        update={"nodes": nodes, "revision": graph.revision + 1, "base_hash": None}
    )


def without(graph: SceneGraph, node_ids) -> SceneGraph:
    """A layout with something set aside, for testing a relaxation only.

    This is never a proposal. Inventory is not adjustable, so removing a chair
    is a question for the owner and this exists to find out whether asking it
    would even help.
    """
    removed = set(node_ids)
    return graph.model_copy(
        update={"nodes": [n for n in graph.nodes if n.id not in removed]}
    )


def unlocked(graph: SceneGraph, node_ids) -> SceneGraph:
    """A layout where something fixed became movable, for testing a relaxation."""
    targets = set(node_ids)
    return graph.model_copy(
        update={
            "nodes": [
                node.model_copy(update={"movable": True})
                if node.id in targets
                else node
                for node in graph.nodes
            ]
        }
    )


def footprint_span(node: SceneNode, axis: tuple[float, float]) -> float:
    """How far the node reaches along `axis`, from its centre."""
    centre = node.transform.position
    return max(
        abs((x - centre.x) * axis[0] + (y - centre.y) * axis[1])
        for x, y in footprint(node)
    )
