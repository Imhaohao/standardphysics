"""Tests for discovery of surface-attached outlets (PIPE-01, PIPE-02).

Validates:
- PIPE-01: Actual production discovery entry with calibrated wall/mesh and detector transport
  attaches detected outlet to surface and returns it through DiscoveryResult without being
  discarded by solid carving.
- PIPE-02: Replaying the same full discovery inputs produces identical stable outlet IDs and
  no duplicate evidence or nodes.
"""

from __future__ import annotations

import json
import pathlib
import uuid

import numpy as np
import pytest
from PIL import Image
from standardphysics_contracts import (
    LidarMesh,
    LidarMeshPart,
    Mat4,
    PoseRecord,
    SceneGraph,
    SceneNode,
    Vec3,
)
from standardphysics_pipeline.coords import capture_to_room
from standardphysics_pipeline.discovery.discover import (
    DiscoveryInputs,
    discover_objects,
)


def create_synthetic_discovery_fixture(tmp_path: pathlib.Path):
    """Creates synthetic wall, LiDAR mesh, camera pose, and photo for discovery."""
    scan_id = uuid.uuid4()
    wall_id = uuid.uuid4()

    # Wall at Y = 2.0, dimensions: width 4m (X), thickness 0.1m (Y), height 2.4m (Z), center (0, 2.0, 1.2)
    wall_node = SceneNode(
        id=wall_id,
        kind="wall",
        label="Wall",
        raw_category="wall",
        dimensions=Vec3(x=4.0, y=0.1, z=2.4),
        transform=Mat4(m=[
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 2.0,
            0.0, 0.0, 1.0, 1.2,
            0.0, 0.0, 0.0, 1.0,
        ]),
        quality="measured",
        movable=False,
    )

    graph = SceneGraph(
        scan_id=scan_id,
        nodes=[wall_node],
        capture_to_room=capture_to_room(0.0),
        revision=1,
    )

    # Synthetic LiDAR mesh: dense grid on the front surface of the wall (Y_room = 1.95 -> Z_arkit = -1.95)
    xs = np.linspace(-1.0, 1.0, 51)
    ys = np.linspace(0.5, 1.9, 51)
    grid_x, grid_y = np.meshgrid(xs, ys)
    grid_z = np.full_like(grid_x, -1.95)
    points_arkit = np.stack([grid_x.ravel(), grid_y.ravel(), grid_z.ravel()], axis=1)
    vertices = [float(v) for v in points_arkit.ravel()]

    triangles = []
    nx, ny = len(xs), len(ys)
    for j in range(ny - 1):
        for i in range(nx - 1):
            idx0 = j * nx + i
            idx1 = idx0 + 1
            idx2 = (j + 1) * nx + i
            idx3 = idx2 + 1
            triangles.extend([idx0, idx1, idx2, idx1, idx3, idx2])

    # Column-major identity matrix
    identity_16 = [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]
    mesh = LidarMesh(
        parts=[
            LidarMeshPart(
                id=uuid.uuid4(),
                transform=identity_16,
                vertices=vertices,
                triangles=triangles,
            )
        ]
    )
    mesh_path = tmp_path / "lidar-mesh.json"
    mesh_path.write_text(mesh.model_dump_json())

    # Camera at (0, 0, 1.2) looking at wall (0, 2.0, 1.2), forward = +Y
    cam_to_arkit = [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 1.2, 0.0, 1.0,
    ]
    pose = PoseRecord(
        metadata_version=2,
        frame_id="frame-0001",
        image="frame-0001.jpg",
        timestamp=100.0,
        transform=cam_to_arkit,
        intrinsics=[500.0, 0.0, 0.0, 0.0, 500.0, 0.0, 320.0, 240.0, 1.0],
        orientation="landscape_right",
        image_width=640,
        image_height=480,
        calibration_width=640,
        calibration_height=480,
        image_orientation="sensor",
    )
    poses_path = tmp_path / "poses.json"
    poses_path.write_text(json.dumps([pose.model_dump(mode="json")]))

    # Synthetic image (640x480)
    img = Image.new("RGB", (640, 480), color=(200, 200, 200))
    img_path = tmp_path / "frame-0001.jpg"
    img.save(img_path)

    frame_paths = {"frame-0001": img_path}

    inputs = DiscoveryInputs(
        graph=graph,
        poses_path=poses_path,
        frame_paths=frame_paths,
        lidar_mesh_path=mesh_path,
    )
    return inputs, wall_node


def test_pipe_01_surface_outlet_persisted_not_discarded_by_solid_carving(tmp_path: pathlib.Path):
    """PIPE-01: Production discovery entry attaches detected outlet to surface and returns it."""
    inputs, wall_node = create_synthetic_discovery_fixture(tmp_path)

    # Fixture transport returning an outlet detection in the center of the frame
    # box in normalized 0-1000: [ymin, xmin, ymax, xmax] -> [450, 450, 550, 550]
    def fixture_transport(prompt: str, schema: dict, headers: dict) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "objects": [
                                {
                                    "name": "outlet",
                                    "box_2d": [450, 450, 550, 550],
                                    "movable": False,
                                    "confidence": 0.95,
                                }
                            ]
                        })
                    }
                }
            ]
        }

    result = discover_objects(inputs, transport=fixture_transport)

    # Verify an outlet node is returned
    outlet_nodes = [n for n in result.nodes if n.kind == "outlet" or (n.attachment and n.attachment.support_type != "unanchored")]
    assert len(outlet_nodes) == 1, f"Expected 1 outlet node, got {len(outlet_nodes)}: {result.nodes}"

    outlet = outlet_nodes[0]
    assert outlet.kind == "outlet"
    assert outlet.attachment is not None
    assert outlet.attachment.support_node_id == wall_node.id
    assert outlet.attachment.support_type == "lidar_surface"
    assert len(outlet.attachment.observations) == 1
    assert outlet.attachment.observations[0].frame_id == "frame-0001"


def test_pipe_02_replay_same_discovery_inputs_twice(tmp_path: pathlib.Path):
    """PIPE-02: Replaying the same discovery inputs twice produces stable IDs and no duplicate evidence."""
    inputs, wall_node = create_synthetic_discovery_fixture(tmp_path)

    def fixture_transport(prompt: str, schema: dict, headers: dict) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "objects": [
                                {
                                    "name": "outlet",
                                    "box_2d": [450, 450, 550, 550],
                                    "movable": False,
                                    "confidence": 0.95,
                                }
                            ]
                        })
                    }
                }
            ]
        }

    res1 = discover_objects(inputs, transport=fixture_transport)
    res2 = discover_objects(inputs, transport=fixture_transport)

    assert len(res1.nodes) == len(res2.nodes)
    outlets_1 = [n for n in res1.nodes if n.attachment is not None]
    outlets_2 = [n for n in res2.nodes if n.attachment is not None]

    assert len(outlets_1) == 1
    assert len(outlets_2) == 1

    node_1 = outlets_1[0]
    node_2 = outlets_2[0]

    # Stable deterministic ID
    assert node_1.id == node_2.id
    # Positions match
    assert node_1.transform.m == pytest.approx(node_2.transform.m, abs=1e-5)
    # No duplicate evidence
    assert len(node_1.attachment.observations) == 1
    assert len(node_2.attachment.observations) == 1
    assert node_1.attachment.observations[0].frame_id == node_2.attachment.observations[0].frame_id
