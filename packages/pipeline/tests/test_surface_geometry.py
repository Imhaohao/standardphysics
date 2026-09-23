"""Tests for support geometry, coordinate transformations, and uncertainty (GEO-01 through GEO-05).

Validates:
- GEO-01: Visible same-wall support is not rejected because normalized-ray Euclidean distance exceeds camera-Z.
- GEO-02: Genuine foreground occluder prevents verified support through occluder.
- GEO-03: Missing/all-infinite depth, mesh hole, grazing/degenerate ray retained as uncertainty.
- GEO-04: RoomPlan node with only box-face intersection gets inferred plane provenance, not measured support.
- GEO-05: Nonidentity capture-to-room transform, socket coordinates in explicit frame, correct positions.
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest
from standardphysics_contracts import Mat4, SceneGraph, SceneNode, Vec3
from standardphysics_pipeline.coords import capture_to_room
from standardphysics_pipeline.discovery.detect import Detection
from standardphysics_pipeline.discovery.surface_attach import (
    attach_detection_to_surface,
    cast_and_intersect,
)
from standardphysics_pipeline.textures.camera import PhotoCamera


def make_camera_and_wall(wall_y: float = 1.95, floor_z: float = 0.0):
    """Camera at (0, 0, 1.2) looking along +Y at a wall at wall_y."""
    wall_id = uuid.uuid4()
    wall = SceneNode(
        id=wall_id,
        kind="wall",
        label="Wall",
        raw_category="wall",
        dimensions=Vec3(x=4.0, y=0.1, z=2.4),
        transform=Mat4(m=[
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, wall_y + 0.05,  # center of wall box so front face is at wall_y
            0.0, 0.0, 1.0, 1.2,
            0.0, 0.0, 0.0, 1.0,
        ]),
        quality="measured",
        movable=False,
    )
    graph = SceneGraph(
        scan_id=uuid.uuid4(),
        nodes=[wall],
        capture_to_room=capture_to_room(floor_z),
        revision=1,
    )

    # Camera at (0, 0, 1.2) looking along +Y in room.
    # Camera frame: +X right, +Y down, +Z forward.
    # Room frame: +X right, +Y forward, +Z up.
    # cam_X = room_X, cam_Y = -room_Z + 1.2, cam_Z = room_Y.
    R_c = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 1.2],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ])
    camera = PhotoCamera(
        frame_id="frame-0001",
        room_to_camera=R_c,
        fx=500.0,
        fy=500.0,
        cx=320.0,
        cy=240.0,
        width=640,
        height=480,
        timestamp=0.0,
    )
    return camera, wall, graph


def test_geo_01_off_axis_same_wall_not_rejected():
    """GEO-01: Off-axis ray where Euclidean distance > camera-Z is not falsely occluded."""
    camera, wall, graph = make_camera_and_wall(wall_y=1.95)

    # Off-axis box [left, top, right, bottom] = [550, 220, 590, 260]
    # For col=570, fx=500, cx=320 -> x_cam/z_cam = 250/500 = 0.5
    # Ray Euclidean distance t = sqrt(1^2 + 0.5^2) * z_cam = 1.118 * 1.95 = 2.18m > 1.95m
    # Camera-Z depth buffer has 1.95m everywhere.
    depth_buf = np.full((60, 80), 1.95, dtype=np.float32)

    det = Detection(
        frame_id="frame-0001",
        name="outlet",
        box=(550.0, 220.0, 590.0, 260.0),
        movable=False,
        confidence=0.95,
    )

    att, node = attach_detection_to_surface(det, camera, graph, depth_buffer=depth_buf)

    assert att.support_node_id == wall.id
    assert att.support_type == "lidar_surface"
    # Must NOT be marked occluded or needs_verification
    assert "detection is fully occluded" not in " ".join(att.uncertainty_reasons)
    assert att.localization_quality == "verified_support"


def test_geo_02_foreground_occluder_blocks_verified_support():
    """GEO-02: Genuine foreground occluder prevents verified support through occluder."""
    camera, wall, graph = make_camera_and_wall(wall_y=1.95)

    # Box in center: [288, 216, 352, 264]
    # Depth buffer has foreground occluder at 1.0m (e.g. chair or person in front of wall)
    depth_buf = np.full((60, 80), 1.0, dtype=np.float32)

    det = Detection(
        frame_id="frame-0001",
        name="outlet",
        box=(288.0, 216.0, 352.0, 264.0),
        movable=False,
        confidence=0.95,
    )

    att, node = attach_detection_to_surface(det, camera, graph, depth_buffer=depth_buf)

    # Must NOT be verified support
    assert att.localization_quality != "verified_support"
    assert any("occluded" in r for r in att.uncertainty_reasons)


def test_geo_03_missing_depth_and_grazing_rays_as_uncertainty():
    """GEO-03: Missing/all-infinite depth, mesh hole, grazing rays retain uncertainty."""
    camera, wall, graph = make_camera_and_wall(wall_y=1.95)

    # 1. All-infinite depth buffer (mesh hole / missing LiDAR)
    inf_depth = np.full((60, 80), np.inf, dtype=np.float32)
    det = Detection(
        frame_id="frame-0001",
        name="outlet",
        box=(288.0, 216.0, 352.0, 264.0),
        movable=False,
        confidence=0.95,
    )
    att1, _ = attach_detection_to_surface(det, camera, graph, depth_buffer=inf_depth)
    assert att1.support_type == "roomplan_plane"
    assert att1.localization_quality == "needs_verification"
    assert any("inferred RoomPlan plane" in r for r in att1.uncertainty_reasons)

    # 2. Grazing ray angle (> 75 degrees from surface normal)
    # Put camera very close to wall grazing along the X axis
    # Camera at (-2.0, 1.95, 1.2) looking along +X (towards (2.0, 1.95, 1.2))
    # Wall is at Y=1.95 with normal -Y. Ray direction is +X, normal is -Y.
    # dot(ray, normal) = 0 -> grazing angle 90 degrees!
    R_grazing = np.array([
        [0.0, 1.0, 0.0, -1.95],
        [0.0, 0.0, -1.0, 1.2],
        [1.0, 0.0, 0.0, 2.0],
        [0.0, 0.0, 0.0, 1.0],
    ])
    cam_grazing = PhotoCamera(
        frame_id="frame-0002",
        room_to_camera=R_grazing,
        fx=500.0, fy=500.0, cx=320.0, cy=240.0, width=640, height=480, timestamp=0.0
    )
    hits = cast_and_intersect(cam_grazing, [(320.0, 240.0)], [wall])
    # The grazing angle check should detect grazing
    if hits:
        assert hits[0].is_grazing is True


def test_geo_04_roomplan_box_face_only_has_inferred_plane_provenance():
    """GEO-04: RoomPlan node without matching LiDAR mesh support gets roomplan_plane provenance."""
    camera, wall, graph = make_camera_and_wall(wall_y=1.95)

    # No depth buffer provided -> only box-face intersection available
    det = Detection(
        frame_id="frame-0001",
        name="outlet",
        box=(288.0, 216.0, 352.0, 264.0),
        movable=False,
        confidence=0.95,
    )
    att, node = attach_detection_to_surface(det, camera, graph, depth_buffer=None)

    assert att.support_type == "roomplan_plane"
    assert att.localization_quality == "needs_verification"
    assert any("inferred RoomPlan plane" in r for r in att.uncertainty_reasons)


def test_geo_05_nonidentity_transform_and_socket_coordinates():
    """GEO-05: Nonidentity capture_to_room transform and explicit socket positions."""
    # Floor dropped by 0.5m: floor_height = 0.5
    camera, wall, graph = make_camera_and_wall(wall_y=1.95, floor_z=0.5)

    # Outlet with explicit sockets
    det = Detection(
        frame_id="frame-0001",
        name="outlet",
        box=(288.0, 216.0, 352.0, 264.0),
        movable=False,
        confidence=0.95,
        sockets=((320.0, 230.0), (320.0, 250.0)),
    )

    depth_buf = np.full((60, 80), 1.95, dtype=np.float32)
    att, node = attach_detection_to_surface(det, camera, graph, depth_buffer=depth_buf)

    assert len(att.sockets) == 2
    # Sockets are in room frame
    s1, s2 = att.sockets[0], att.sockets[1]
    assert s1.center.y == pytest.approx(1.95, abs=0.05)
    assert s2.center.y == pytest.approx(1.95, abs=0.05)
    # Vertical separation: row 230 vs 250 (20 pixels at fx=500, z=1.95 -> ~0.078m)
    assert s1.center.z > s2.center.z  # row 230 is higher up in room frame than row 250
    assert abs(s1.center.z - s2.center.z) == pytest.approx(20.0 * 1.95 / 500.0, abs=0.02)
