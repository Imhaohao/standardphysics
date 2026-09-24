"""DeepFusion-driven Gaussian Splat Model for Standard Physics.

Directly predicts and refines 3D Gaussian parameters (positions, scales, rotations,
opacities, and spherical harmonics) by fusing metric LiDAR geometry with calibrated
multi-view camera features.
"""

from __future__ import annotations

import math
import pathlib
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from standardphysics_pipeline.textures.camera import PhotoCamera

from .deep_fusion import LearnableAlign
from .feature_extractor import ImageFeatureExtractor, PointFeatureEncoder


@dataclass
class GaussianSplatPrediction:
    """Container for predicted 3D Gaussian primitives."""

    positions: np.ndarray  # (N, 3)
    scales: np.ndarray  # (N, 3) in log scale (or linear, see export)
    rotations: np.ndarray  # (N, 4) normalized quaternions (w, x, y, z)
    opacities: np.ndarray  # (N, 1) inverse sigmoid logits
    sh0: np.ndarray  # (N, 3) SH degree 0
    sh_rest: np.ndarray | None = None  # (N, 24) or None for SH degree 2

    def export_ply(self, path: pathlib.Path) -> None:
        """Export Gaussians in official 3DGS binary PLY format for .spz compression."""
        path.parent.mkdir(parents=True, exist_ok=True)
        num_verts = len(self.positions)

        header = f"""ply
format binary_little_endian 1.0
element vertex {num_verts}
property float x
property float y
property float z
property float f_dc_0
property float f_dc_1
property float f_dc_2
property float opacity
property float scale_0
property float scale_1
property float scale_2
property float rot_0
property float rot_1
property float rot_2
property float rot_3
end_header
"""
        with open(path, "wb") as f:
            f.write(header.encode("ascii"))
            data = np.zeros(
                num_verts,
                dtype=[
                    ("x", "f4"), ("y", "f4"), ("z", "f4"),
                    ("f_dc_0", "f4"), ("f_dc_1", "f4"), ("f_dc_2", "f4"),
                    ("opacity", "f4"),
                    ("scale_0", "f4"), ("scale_1", "f4"), ("scale_2", "f4"),
                    ("rot_0", "f4"), ("rot_1", "f4"), ("rot_2", "f4"), ("rot_3", "f4"),
                ],
            )
            data["x"] = self.positions[:, 0]
            data["y"] = self.positions[:, 1]
            data["z"] = self.positions[:, 2]
            data["f_dc_0"] = self.sh0[:, 0]
            data["f_dc_1"] = self.sh0[:, 1]
            data["f_dc_2"] = self.sh0[:, 2]
            data["opacity"] = self.opacities[:, 0]
            data["scale_0"] = self.scales[:, 0]
            data["scale_1"] = self.scales[:, 1]
            data["scale_2"] = self.scales[:, 2]
            data["rot_0"] = self.rotations[:, 0]
            data["rot_1"] = self.rotations[:, 1]
            data["rot_2"] = self.rotations[:, 2]
            data["rot_3"] = self.rotations[:, 3]
            f.write(data.tobytes())


class DeepFusionGaussianModel(nn.Module):
    """Predicts structured 3D Gaussian primitives from fused LiDAR + Camera features."""

    def __init__(
        self,
        point_dim: int = 64,
        image_dim: int = 64,
        hidden_dim: int = 64,
        base_log_scale: float = math.log(0.02),  # ~2cm default
        max_position_offset_m: float = 0.03,  # max 3cm shift from LiDAR
    ):
        super().__init__()
        self.base_log_scale = base_log_scale
        self.max_position_offset_m = max_position_offset_m

        self.point_encoder = PointFeatureEncoder(in_dim=6, out_dim=point_dim)
        self.image_encoder = ImageFeatureExtractor(in_channels=3, feature_dim=image_dim)
        self.align = LearnableAlign(point_dim=point_dim, image_dim=image_dim, hidden_dim=hidden_dim)

        # Attribute prediction heads
        # 1. Delta position: small residual to snap Gaussians to true optical surface
        self.pos_head = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.SiLU(inplace=True),
            nn.Linear(32, 3),
            nn.Tanh(),
        )

        # 2. Anisotropic log scale: delta relative to base_log_scale
        self.scale_head = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.SiLU(inplace=True),
            nn.Linear(32, 3),
        )

        # 3. Rotation quaternion (w, x, y, z)
        self.rot_head = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.SiLU(inplace=True),
            nn.Linear(32, 4),
        )

        # 4. Opacity logit
        self.opac_head = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.SiLU(inplace=True),
            nn.Linear(32, 1),
        )

        # 5. Base color (SH degree 0)
        self.color_head = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.SiLU(inplace=True),
            nn.Linear(64, 3),
        )

    def forward(
        self,
        points: torch.Tensor,
        normals: torch.Tensor | None,
        cameras: Sequence[PhotoCamera],
        images: list[torch.Tensor] | torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        """Forward pass predicting Gaussian attributes for each point.

        Args:
            points: (N, 3) LiDAR coordinates in room frame.
            normals: (N, 3) surface normals or None.
            cameras: List of M PhotoCamera objects.
            images: List of M tensors (1, 3, H, W) or (M, 3, H, W).

        Returns:
            Dict containing predicted positions, log_scales, quats, inv_opacities, and sh0.
        """
        device = points.device

        # 1. Encode LiDAR points
        if normals is None:
            normals = torch.tensor([0.0, 0.0, 1.0], device=device).expand_as(points)
        pt_geom = torch.cat([points, normals], dim=-1)
        point_features = self.point_encoder(pt_geom)

        # 2. Extract 2D feature maps
        if isinstance(images, list):
            feature_maps = [self.image_encoder(img) for img in images]
        else:
            feature_maps = self.image_encoder(images)

        # 3. LearnableAlign cross-modality fusion
        fused_features, visibility = self.align(point_features, points, cameras, feature_maps)

        # 4. Predict Gaussian parameters
        # Position: base LiDAR + bounded offset
        delta_pos = self.pos_head(fused_features) * self.max_position_offset_m
        pred_positions = points + delta_pos

        # Scales: base scale + learned delta
        delta_scale = self.scale_head(fused_features)
        pred_log_scales = self.base_log_scale + delta_scale

        # Rotations: quaternion normalized
        raw_quats = self.rot_head(fused_features)
        # Initialize with identity prior [1, 0, 0, 0]
        raw_quats[:, 0] = raw_quats[:, 0] + 1.0
        pred_quats = F.normalize(raw_quats, dim=-1)

        # Opacities: higher for points with multi-view visibility
        pred_inv_opacities = self.opac_head(fused_features)
        # Penalize unobserved points
        pred_inv_opacities = torch.where(
            visibility.unsqueeze(-1),
            pred_inv_opacities,
            pred_inv_opacities - 2.0,  # lower opacity for unseen vertices
        )

        # Colors: SH0 representation
        pred_sh0 = self.color_head(fused_features)

        return {
            "positions": pred_positions,
            "log_scales": pred_log_scales,
            "quats": pred_quats,
            "inv_opacities": pred_inv_opacities,
            "sh0": pred_sh0,
            "visibility": visibility,
        }

    @staticmethod
    def scale_anisotropy_loss(log_scales: torch.Tensor, max_ratio: float = 3.0) -> torch.Tensor:
        """Penalize Gaussians whose aspect ratio exceeds max_ratio to prevent needles."""
        scales = torch.exp(log_scales)
        max_scale, _ = torch.max(scales, dim=-1)
        min_scale, _ = torch.min(scales, dim=-1)
        ratio = max_scale / (min_scale + 1e-6)
        penalty = F.relu(ratio - max_ratio)
        return penalty.mean()

    def predict_splats(
        self,
        points: np.ndarray,
        normals: np.ndarray | None,
        cameras: Sequence[PhotoCamera],
        images: list[np.ndarray],
    ) -> GaussianSplatPrediction:
        """Convenience inference function accepting numpy arrays."""
        self.eval()
        device = next(self.parameters()).device

        with torch.no_grad():
            pts_t = torch.from_numpy(points).float().to(device)
            norms_t = torch.from_numpy(normals).float().to(device) if normals is not None else None

            # Convert images to torch tensors (1, 3, H, W) normalized to [0, 1]
            img_tensors = []
            for img in images:
                # Assuming img is H x W x 3 uint8 or float
                if img.dtype == np.uint8:
                    img_float = img.astype(np.float32) / 255.0
                else:
                    img_float = img.astype(np.float32)
                t = torch.from_numpy(img_float).permute(2, 0, 1).unsqueeze(0).to(device)
                img_tensors.append(t)

            preds = self.forward(pts_t, norms_t, cameras, img_tensors)

            pos = preds["positions"].cpu().numpy()
            log_s = preds["log_scales"].cpu().numpy()
            quats = preds["quats"].cpu().numpy()
            inv_opac = preds["inv_opacities"].cpu().numpy()
            sh = preds["sh0"].cpu().numpy()

            return GaussianSplatPrediction(
                positions=pos,
                scales=log_s,
                rotations=quats,
                opacities=inv_opac,
                sh0=sh,
            )
