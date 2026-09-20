"""Tests for multi-view reconciliation, anti-transitivity, and preventing incorrect merges."""

from __future__ import annotations

import math
import uuid
import numpy as np
import pytest
from standardphysics_contracts import Mat4, ObservationCrop, SceneNode, SocketTarget, SurfaceAttachment, Vec3
from standardphysics_pipeline.discovery.reconcile import (
    are_compatible_observations,
    merge_two_nodes,
    reconcile_outlets,
)


def outlet_node(
    centre: tuple[float, float, float],
    normal: tuple[float, float, float],
    support_id: uuid.UUID,
    frame_id: str,
    sockets: list[tuple[float, float, float]] | None = None,
) -> SceneNode:
    norm = np.array(normal, dtype=float)
    norm /= np.linalg.norm(norm)
    up = np.array([0.0, 0.0, 1.0])
    tangent = np.cross(norm, up)
    if np.linalg.norm(tangent) < 1e-4:
        tangent = np.array([1.0, 0.0, 0.0])
    else:
        tangent /= np.linalg.norm(tangent)
    bitangent = np.cross(norm, tangent)
    rot = np.column_stack([tangent, norm, bitangent])

    socket_targets = []
    if sockets:
        for i, (sx, sy, sz) in enumerate(sockets):
            socket_targets.append(SocketTarget(
                id=f"{frame_id}_s{i}",
                center=Vec3(x=sx, y=sy, z=sz),
                status="observed",
                confidence=0.9,
            ))

    att = SurfaceAttachment(
        support_node_id=support_id,
        support_type="lidar_surface",
        normal=Vec3(x=float(norm[0]), y=float(norm[1]), z=float(norm[2])),
        sockets=socket_targets,
        observations=[ObservationCrop(frame_id=frame_id, sensor_box=[100, 100, 200, 200], confidence=0.9)],
        localization_quality="verified_support",
    )

    return SceneNode(
        id=uuid.uuid4(),
        kind="outlet",
        label=f"Outlet ({frame_id})",
        raw_category="outlet",
        dimensions=Vec3(x=0.12, y=0.03, z=0.12),
        transform=Mat4(m=[
            rot[0, 0], rot[0, 1], rot[0, 2], float(centre[0]),
            rot[1, 0], rot[1, 1], rot[1, 2], float(centre[1]),
            rot[2, 0], rot[2, 1], rot[2, 2], float(centre[2]),
            0.0, 0.0, 0.0, 1.0,
        ]),
        parent_id=support_id,
        relation="mounted_on",
        attachment=att,
    )


class TestReconciliation:
    def test_same_outlet_in_two_views_merges(self):
        wall_id = uuid.uuid4()
        # Same outlet at (1.0, 2.0, 0.4) observed in frame-01 and frame-02 (slight noise 1cm)
        n1 = outlet_node((1.0, 2.0, 0.4), (0.0, -1.0, 0.0), wall_id, "frame-01")
        n2 = outlet_node((1.01, 2.0, 0.41), (0.0, -1.0, 0.0), wall_id, "frame-02")
        assert are_compatible_observations(n1, n2) is True
        merged = reconcile_outlets([n1, n2])
        assert len(merged) == 1
        assert len(merged[0].attachment.observations) == 2
        # Position averaged
        assert merged[0].transform.m[3] == pytest.approx(1.005, abs=1e-3)

    def test_two_adjacent_outlets_do_not_merge(self):
        wall_id = uuid.uuid4()
        # Adjacent outlets separated by 15 cm along the wall (+X)
        n1 = outlet_node((1.0, 2.0, 0.4), (0.0, -1.0, 0.0), wall_id, "frame-01")
        n2 = outlet_node((1.15, 2.0, 0.4), (0.0, -1.0, 0.0), wall_id, "frame-02")
        assert are_compatible_observations(n1, n2) is False
        reconciled = reconcile_outlets([n1, n2])
        assert len(reconciled) == 2

    def test_opposite_sides_of_wall_do_not_merge(self):
        wall_id = uuid.uuid4()
        # Outlets back-to-back on opposite sides of a 10cm wall
        n1 = outlet_node((1.0, 1.95, 0.4), (0.0, -1.0, 0.0), wall_id, "frame-01")
        n2 = outlet_node((1.0, 2.05, 0.4), (0.0, 1.0, 0.0), wall_id, "frame-02") # Normal +Y
        assert are_compatible_observations(n1, n2) is False
        reconciled = reconcile_outlets([n1, n2])
        assert len(reconciled) == 2

    def test_different_support_walls_do_not_merge(self):
        wall1 = uuid.uuid4()
        wall2 = uuid.uuid4()
        n1 = outlet_node((1.0, 2.0, 0.4), (0.0, -1.0, 0.0), wall1, "frame-01")
        n2 = outlet_node((1.0, 2.0, 0.4), (0.0, -1.0, 0.0), wall2, "frame-02")
        assert are_compatible_observations(n1, n2) is False
        reconciled = reconcile_outlets([n1, n2])
        assert len(reconciled) == 2

    def test_reconcile_idempotence(self):
        wall_id = uuid.uuid4()
        n1 = outlet_node((1.0, 2.0, 0.4), (0.0, -1.0, 0.0), wall_id, "frame-01")
        n2 = outlet_node((1.01, 2.0, 0.41), (0.0, -1.0, 0.0), wall_id, "frame-02")
        n3 = outlet_node((2.0, 2.0, 0.4), (0.0, -1.0, 0.0), wall_id, "frame-03")
        once = reconcile_outlets([n1, n2, n3])
        twice = reconcile_outlets(once)
        assert len(once) == len(twice) == 2
        assert once[0].transform.m == twice[0].transform.m
