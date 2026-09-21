"""Feature extraction for 2D images and 3D LiDAR geometry."""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class ImageFeatureExtractor(nn.Module):
    """Lightweight 2D convolutional feature extractor for video keyframes.

    Extracts deep visual features at 1/4 resolution, suitable for fast cross-attention
    with 3D LiDAR point queries.
    """

    def __init__(self, in_channels: int = 3, feature_dim: int = 64):
        super().__init__()
        self.feature_dim = feature_dim

        # Initial stem: downsample by 2
        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.SiLU(inplace=True),
            nn.Conv2d(32, 32, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.SiLU(inplace=True),
        )

        # Stage 1: downsample by 2 (total 1/4 resolution)
        self.stage1 = nn.Sequential(
            nn.Conv2d(32, 48, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(48),
            nn.SiLU(inplace=True),
            nn.Conv2d(48, 48, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(48),
            nn.SiLU(inplace=True),
        )

        # Stage 2: residual refine block
        self.conv_res = nn.Conv2d(48, feature_dim, kernel_size=1, bias=False)
        self.block = nn.Sequential(
            nn.Conv2d(48, feature_dim, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(feature_dim),
            nn.SiLU(inplace=True),
            nn.Conv2d(feature_dim, feature_dim, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(feature_dim),
        )
        self.out_act = nn.SiLU(inplace=True)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        """Extract feature maps from images of shape (B, 3, H, W).

        Returns:
            Tensor of shape (B, feature_dim, H/4, W/4).
        """
        x = self.stem(images)
        x = self.stage1(x)
        residual = self.conv_res(x)
        x = self.out_act(self.block(x) + residual)
        return x

    @staticmethod
    def sample_features(
        feature_map: torch.Tensor,
        u: torch.Tensor,
        v: torch.Tensor,
        image_width: int,
        image_height: int,
    ) -> torch.Tensor:
        """Sample feature map at pixel coordinates (u, v).

        Args:
            feature_map: Tensor of shape (B, C, H_feat, W_feat)
            u: Tensor of shape (N,) pixel column coordinates [0, image_width - 1]
            v: Tensor of shape (N,) pixel row coordinates [0, image_height - 1]
            image_width: Calibration/image width
            image_height: Calibration/image height

        Returns:
            Tensor of shape (B, N, C) with sampled feature vectors.
        """
        # Normalize to grid_sample range [-1, 1]
        grid_x = 2.0 * (u / max(image_width - 1, 1)) - 1.0
        grid_y = 2.0 * (v / max(image_height - 1, 1)) - 1.0

        # Grid shape: (1, 1, N, 2)
        grid = torch.stack([grid_x, grid_y], dim=-1).unsqueeze(0).unsqueeze(0)
        if feature_map.dim() == 3:
            feature_map = feature_map.unsqueeze(0)

        B, C, _, _ = feature_map.shape
        # Sample: output shape (B, C, 1, N)
        sampled = F.grid_sample(feature_map, grid.expand(B, -1, -1, -1), mode="bilinear", padding_mode="zeros", align_corners=True)
        # Reshape to (B, N, C)
        return sampled.squeeze(2).permute(0, 2, 1)


class PointFeatureEncoder(nn.Module):
    """Encodes 3D LiDAR positions and surface normals into a geometric embedding."""

    def __init__(self, in_dim: int = 6, out_dim: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 64),
            nn.LayerNorm(64),
            nn.SiLU(inplace=True),
            nn.Linear(64, out_dim),
            nn.LayerNorm(out_dim),
        )

    def forward(self, points_and_normals: torch.Tensor) -> torch.Tensor:
        """Encode points of shape (N, 6) or (N, 3) into (N, out_dim)."""
        if points_and_normals.shape[-1] == 3:
            # Pad with default up normal if normals are absent
            up_normal = torch.tensor([0.0, 0.0, 1.0], device=points_and_normals.device, dtype=points_and_normals.dtype)
            normals = up_normal.expand_as(points_and_normals)
            points_and_normals = torch.cat([points_and_normals, normals], dim=-1)
        return self.net(points_and_normals)
