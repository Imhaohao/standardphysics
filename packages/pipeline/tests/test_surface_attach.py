"""Tests for surface attachment, ray-plane intersection, occlusions, and uncertainty caveats."""

from __future__ import annotations

import math
import uuid
import numpy as np
import pytest
from standardphysics_contracts import Mat4, SceneGraph, SceneNode, Vec3
from standardphysics_pipeline.coords import capture_to_room
from standardphysics_pipeline.discovery.detect import Detection
from standardphysics_pipeline.discovery.surface_attach import (
    attach_detection_to_surface,
    intersect_node_surface,
    ray_for_pixel,
)
from standardphysics_pipeline.textures.camera import PhotoCamera


def camera_at(position, looking_at, width=640, height=480, focal=500.0) -> PhotoCamera:
    """A camera in the room frame, +X right, +Y down, +Z forward."""
    forward = np.asarray(looking_at, dtype=float) - np.asarray(position, dtype=float)
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    rotation = np.stack([right, down, forward])
    return PhotoCamera(
        frame_id="frame-0001",
        room_to_camera=np.vstack([
            np.hstack([rotation, (-rotation @ np.asarray(position, dtype=float)).reshape(3, 1)]),
            [0.0, 0.0, 0.0, 1.0],
        ]),
        fx=focal, fy=focal, cx=width / 2 - 0.5, cy=height / 2 - 0.5,
        width=width, height=height, timestamp=0.0,
    )


def wall_node(centre, size, *, yaw=0.0, quality="measured") -> SceneNode:
    """A vertical wall node standing in room frame."""
    cos_t, sin_t = math.cos(yaw), math.sin(yaw)
    return SceneNode(
        id=uuid.uuid4(),
        kind="wall",
        label="Wall",
        raw_category="wall",
        dimensions=Vec3(x=size[0], y=size[1], z=size[2]),
        transform=Mat4(m=[
            cos_t, -sin_t, 0.0, centre[0],
            sin_t, cos_t, 0.0, centre[1],
            0.0, 0.0, 1.0, centre[2],
            0.0, 0.0, 0.0, 1.0,
        ]),
        quality=quality,
        movable=False,
    )


class TestSurfaceAttachmentProjection:
    def test_ray_for_pixel_points_towards_target(self):
        cam = camera_at((0.0, 0.0, 1.0), (0.0, 2.0, 1.0))
        origin, direction = ray_for_pixel(cam, cam.cx, cam.cy)
        assert origin == pytest.approx([0.0, 0.0, 1.0])
        # Principal ray should point along +Y
        assert direction == pytest.approx([0.0, 1.0, 0.0], abs=1e-3)

    def test_intersect_node_surface_hits_wall(self):
        # Wall at Y=2.0, size 3m wide (X), 0.1m thick (Y), 2.5m tall (Z)
        wall = wall_node((0.0, 2.0, 1.25), (3.0, 0.1, 2.5))
        origin = np.array([0.0, 0.0, 1.0])
        direction = np.array([0.0, 1.0, 0.0])
        res = intersect_node_surface(origin, direction, wall)
        assert res is not None
        t, hit_point, normal = res
        # Face is at Y = 2.0 - 0.05 = 1.95
        assert t == pytest.approx(1.95, abs=0.01)
        assert hit_point[1] == pytest.approx(1.95, abs=0.01)
        # Normal points towards camera (-Y)
        assert normal == pytest.approx([0.0, -1.0, 0.0], abs=1e-3)

    def test_attach_detection_to_wall_produces_anchored_node(self):
        wall = wall_node((0.0, 2.0, 1.25), (3.0, 0.1, 2.5))
        graph = SceneGraph(scan_id=uuid.uuid4(), nodes=[wall], capture_to_room=capture_to_room(0.0))
        cam = camera_at((0.0, 0.0, 1.0), (0.0, 2.0, 1.0))
        # Center detection box in pixels: [300, 220, 340, 260] around principal point (319.5, 239.5)
        detection = Detection(
            frame_id="frame-0001",
            name="electrical outlet",
            box=(300.0, 220.0, 340.0, 260.0),
            movable=False,
            confidence=0.95,
            category="outlet",
            sockets=((320.0, 230.0), (320.0, 250.0)),
        )
        depth_buffer = np.full((480, 640), 1.95)
        attachment, outlet_node = attach_detection_to_surface(detection, cam, graph, depth_buffer=depth_buffer)
        assert attachment.support_node_id == wall.id
        assert attachment.support_type == "lidar_surface"
        assert attachment.localization_quality == "verified_support"
        assert len(attachment.sockets) == 2
        assert outlet_node.kind == "outlet"
        assert outlet_node.parent_id == wall.id
        assert outlet_node.relation == "mounted_on"
        # Y position of outlet node should match wall face
        assert outlet_node.transform.m[7] == pytest.approx(1.95, abs=0.02)

    def test_occluded_detection_flags_uncertainty(self):
        wall = wall_node((0.0, 4.0, 1.25), (3.0, 0.1, 2.5))
        graph = SceneGraph(scan_id=uuid.uuid4(), nodes=[wall], capture_to_room=capture_to_room(0.0))
        cam = camera_at((0.0, 0.0, 1.0), (0.0, 4.0, 1.0))
        detection = Detection(
            frame_id="frame-0001",
            name="outlet",
            box=(300.0, 220.0, 340.0, 260.0),
            movable=False,
            confidence=0.95,
            category="outlet",
        )
        # Depth buffer indicates an obstacle at depth 1.0m (while wall is at ~3.95m)
        depth_buf = np.full((480, 640), 1.0, dtype=np.float32)
        attachment, node = attach_detection_to_surface(detection, cam, graph, depth_buffer=depth_buf)
        assert attachment.localization_quality == "unanchored"
        assert any("occluded" in r for r in attachment.uncertainty_reasons)

    def test_missing_geometry_produces_unanchored_candidate(self):
        # Empty graph with no walls
        graph = SceneGraph(scan_id=uuid.uuid4(), nodes=[], capture_to_room=capture_to_room(0.0))
        cam = camera_at((0.0, 0.0, 1.0), (0.0, 2.0, 1.0))
        detection = Detection(
            frame_id="frame-0001",
            name="outlet",
            box=(300.0, 220.0, 340.0, 260.0),
            movable=False,
            confidence=0.90,
            category="outlet",
        )
        attachment, node = attach_detection_to_surface(detection, cam, graph)
        assert attachment.support_type == "unanchored"
        assert attachment.support_node_id is None
        assert node.kind == "candidate_outlet"
        assert any("no support surface" in r for r in attachment.uncertainty_reasons)

    def test_surface_attached_node_is_not_solid_obstacle(self):
        wall = wall_node((0.0, 2.0, 1.25), (3.0, 0.1, 2.5))
        graph = SceneGraph(scan_id=uuid.uuid4(), nodes=[wall], capture_to_room=capture_to_room(0.0))
        cam = camera_at((0.0, 0.0, 1.0), (0.0, 2.0, 1.0))
        detection = Detection("f1", "outlet", (300.0, 220.0, 340.0, 260.0), False, 0.95, category="outlet")
        _, outlet_node = attach_detection_to_surface(detection, cam, graph)
        graph.nodes.append(outlet_node)
        obstacles = graph.obstacles()
        # Wall is an obstacle; outlet must NOT be in obstacles!
        assert wall in obstacles
        assert outlet_node not in obstacles

    def test_grazing_rays_flagged_with_uncertainty(self):
        # Wall at Y=2.0 with normal (0, -1, 0)
        wall = wall_node((0.0, 2.0, 1.25), (10.0, 0.1, 2.5))
        graph = SceneGraph(scan_id=uuid.uuid4(), nodes=[wall], capture_to_room=capture_to_room(0.0))
        # Camera at (5.0, 0.5, 1.25) looking towards (0.0, 2.0, 1.25)
        # Direction has dx = -5, dy = 1.5. cos(angle) = 1.5 / sqrt(25 + 2.25) = 1.5 / 5.22 ≈ 0.287 -> grazing!
        # Make angle even shallower: Camera at (8.0, 0.5, 1.25) looking towards (0.0, 2.0, 1.25):
        # dx = -8, dy = 1.5 -> cos(angle) = 1.5 / sqrt(64 + 2.25) = 1.5 / 8.14 ≈ 0.184 < 0.2588
        cam = camera_at((8.0, 0.5, 1.25), (0.0, 2.0, 1.25))
        detection = Detection("f1", "outlet", (300.0, 220.0, 340.0, 260.0), False, 0.95, category="outlet")
        attachment, node = attach_detection_to_surface(detection, cam, graph)
        assert attachment.localization_quality == "needs_verification"
        assert any("grazing angle" in r for r in attachment.uncertainty_reasons)

    def test_near_edge_mixed_supports_flagged(self):
        # Wall from X = -1.0 to +1.0 at Y = 2.0 (width 2.0m)
        wall = wall_node((0.0, 2.0, 1.25), (2.0, 0.1, 2.5))
        graph = SceneGraph(scan_id=uuid.uuid4(), nodes=[wall], capture_to_room=capture_to_room(0.0))
        # Camera at (0.9, 0.0, 1.25) looking at (0.9, 2.0, 1.25) - very close to right edge at X=1.0
        cam = camera_at((0.9, 0.0, 1.25), (0.9, 2.0, 1.25))
        # Wide detection box spanning across the edge of the wall (some rays hit wall X < 1.0, some miss X > 1.0)
        detection = Detection("f1", "outlet", (150.0, 200.0, 500.0, 280.0), False, 0.90, category="outlet")
        attachment, node = attach_detection_to_surface(detection, cam, graph)
        # Should flag partial coverage near surface edge
        assert any("edge or mesh boundary" in r or "mixed support" in r for r in attachment.uncertainty_reasons)

    def test_stale_revision_rejection(self):
        wall = wall_node((0.0, 2.0, 1.25), (3.0, 0.1, 2.5))
        graph = SceneGraph(scan_id=uuid.uuid4(), revision=5, nodes=[wall], capture_to_room=capture_to_room(0.0))
        cam = camera_at((0.0, 0.0, 1.0), (0.0, 2.0, 1.0))
        detection = Detection("f1", "outlet", (300.0, 220.0, 340.0, 260.0), False, 0.95, category="outlet")

        # Passing stale expected_revision=4 raises ValueError
        with pytest.raises(ValueError, match="stale scene graph revision"):
            attach_detection_to_surface(detection, cam, graph, expected_revision=4)

        # Matching expected_revision=5 succeeds
        attachment, node = attach_detection_to_surface(detection, cam, graph, expected_revision=5)
        assert attachment is not None

    def test_thin_mounted_objects_preserved_while_carving_rejects_slivers(self):
        from standardphysics_pipeline.discovery.carve import SLIVER_EXTENT

        wall = wall_node((0.0, 2.0, 1.25), (3.0, 0.1, 2.5))
        graph = SceneGraph(scan_id=uuid.uuid4(), nodes=[wall], capture_to_room=capture_to_room(0.0))
        cam = camera_at((0.0, 0.0, 1.0), (0.0, 2.0, 1.0))
        detection = Detection("f1", "outlet", (300.0, 220.0, 340.0, 260.0), False, 0.95, category="outlet")

        depth_buffer = np.full((480, 640), 1.95)
        attachment, outlet_node = attach_detection_to_surface(detection, cam, graph, depth_buffer=depth_buffer)
        # Outlet thickness is 0.03m (3 cm), which is thinner than SLIVER_EXTENT (0.035m / 3.5cm)
        assert outlet_node.dimensions.y == 0.03
        assert outlet_node.dimensions.y < SLIVER_EXTENT
        # Surface attachment preserves it without discarding
        assert attachment.support_type == "lidar_surface"
        assert outlet_node.kind == "outlet"

