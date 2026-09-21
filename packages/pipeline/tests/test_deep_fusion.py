"""Unit tests for DeepFusion Gaussian Splatting modules.

Torch is a dependency of nothing else here and is declared nowhere, so on a
machine without it these skip. Erroring instead took the whole suite's
collection down over a predictor nothing else depends on.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from standardphysics_pipeline.splats.deep_fusion import InverseAug, LearnableAlign  # noqa: E402
from standardphysics_pipeline.splats.deep_gaussian_model import (  # noqa: E402
    DeepFusionGaussianModel,
    GaussianSplatPrediction,
)
from standardphysics_pipeline.splats.feature_extractor import (  # noqa: E402
    ImageFeatureExtractor,
    PointFeatureEncoder,
)
from standardphysics_pipeline.textures.camera import PhotoCamera  # noqa: E402


def test_inverse_aug_projection():
    camera = PhotoCamera(
        frame_id="frame-001",
        room_to_camera=np.eye(4),
        fx=500.0,
        fy=500.0,
        cx=320.0,
        cy=240.0,
        width=640,
        height=480,
        timestamp=0.0,
    )
    # Point at (0, 0, 2) in camera space
    pts = np.array([[0.0, 0.0, 2.0]], dtype=np.float32)
    u, v, depth = InverseAug.room_to_camera_points(pts, camera)

    assert np.isclose(u[0], 320.0)
    assert np.isclose(v[0], 240.0)
    assert np.isclose(depth[0], 2.0)

    # Test with torch Tensor
    pts_t = torch.from_numpy(pts)
    u_t, v_t, d_t = InverseAug.room_to_camera_points(pts_t, camera)
    assert torch.isclose(u_t[0], torch.tensor(320.0))
    assert torch.isclose(v_t[0], torch.tensor(240.0))
    assert torch.isclose(d_t[0], torch.tensor(2.0))


def test_image_feature_extractor_and_sampling():
    extractor = ImageFeatureExtractor(in_channels=3, feature_dim=32)
    images = torch.zeros((1, 3, 240, 320))
    # Add a pattern
    images[:, :, 100:140, 140:180] = 1.0

    fmap = extractor(images)
    assert fmap.shape == (1, 32, 60, 80)

    u = torch.tensor([160.0, 10.0])
    v = torch.tensor([120.0, 10.0])
    sampled = ImageFeatureExtractor.sample_features(fmap, u, v, 320, 240)
    assert sampled.shape == (1, 2, 32)


def test_point_feature_encoder():
    encoder = PointFeatureEncoder(in_dim=6, out_dim=32)
    pts = torch.randn(10, 6)
    out = encoder(pts)
    assert out.shape == (10, 32)

    # Test with 3D points (auto-normals)
    pts3 = torch.randn(10, 3)
    out3 = encoder(pts3)
    assert out3.shape == (10, 32)


def test_learnable_align_multiview():
    align = LearnableAlign(point_dim=32, image_dim=32, hidden_dim=32)
    N = 5
    point_features = torch.randn(N, 32)
    points = torch.tensor([
        [0.0, 0.0, 2.0],    # In view for camera 1 and 2
        [10.0, 0.0, 2.0],   # Out of view
        [0.0, 0.0, -1.0],   # Behind camera
        [0.1, 0.1, 1.5],    # In view
        [-0.1, -0.1, 2.5],  # In view
    ], dtype=torch.float32)

    cam1 = PhotoCamera("f1", np.eye(4), 500, 500, 320, 240, 640, 480, 0.0)
    cam2 = PhotoCamera("f2", np.eye(4), 500, 500, 320, 240, 640, 480, 1.0)
    cameras = [cam1, cam2]

    fmaps = [torch.randn(1, 32, 60, 80), torch.randn(1, 32, 60, 80)]
    fused, visibility = align(point_features, points, cameras, fmaps)

    assert fused.shape == (N, 32)
    assert visibility.shape == (N,)
    # Points 0, 3, 4 should be visible
    assert visibility[0].item() is True
    assert visibility[1].item() is False  # Out of view
    assert visibility[2].item() is False  # Behind camera
    assert visibility[3].item() is True
    assert visibility[4].item() is True


def test_deep_gaussian_model_forward_and_export(tmp_path: pathlib.Path):
    model = DeepFusionGaussianModel(point_dim=32, image_dim=32, hidden_dim=32)
    N = 8
    points = torch.randn(N, 3)
    points[:, 2] = torch.abs(points[:, 2]) + 1.0  # In front of camera
    normals = torch.randn(N, 3)
    normals = torch.nn.functional.normalize(normals, dim=-1)

    cam = PhotoCamera("f1", np.eye(4), 500, 500, 320, 240, 640, 480, 0.0)
    images = [torch.randn(1, 3, 120, 160)]

    preds = model(points, normals, [cam], images)
    assert preds["positions"].shape == (N, 3)
    assert preds["log_scales"].shape == (N, 3)
    assert preds["quats"].shape == (N, 4)
    assert preds["inv_opacities"].shape == (N, 1)
    assert preds["sh0"].shape == (N, 3)

    # Check quaternion normalization
    quat_norms = torch.norm(preds["quats"], dim=-1)
    assert torch.allclose(quat_norms, torch.ones_like(quat_norms), atol=1e-5)

    # Check scale anisotropy loss
    loss = DeepFusionGaussianModel.scale_anisotropy_loss(preds["log_scales"], max_ratio=3.0)
    assert loss.item() >= 0.0

    # Test PLY export
    splat_pred = GaussianSplatPrediction(
        positions=preds["positions"].detach().numpy(),
        scales=preds["log_scales"].detach().numpy(),
        rotations=preds["quats"].detach().numpy(),
        opacities=preds["inv_opacities"].detach().numpy(),
        sh0=preds["sh0"].detach().numpy(),
    )
    ply_path = tmp_path / "test_splats.ply"
    splat_pred.export_ply(ply_path)
    assert ply_path.is_file()
    assert ply_path.stat().st_size > 0

    # Verify PLY header
    with open(ply_path, "rb") as f:
        header = f.read(256).decode("ascii", errors="ignore")
        assert "element vertex 8" in header
        assert "property float f_dc_0" in header
