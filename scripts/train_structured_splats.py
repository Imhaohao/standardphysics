"""Seed Gaussian splats on the LiDAR surface and export them as .spz.

This is *initialisation only*. It places one isotropic Gaussian per LiDAR vertex, which
is a floater-free and needle-free starting point by construction, and writes the PLY the
.spz converter reads. There is no optimiser, no rasteriser and no photometric or depth
loss here, so the output carries LiDAR geometry and nothing the photos add: flat vertex
colour at best, and no view-dependent shading.

The regularisers a real training loop would need (`scale_anisotropy_loss`,
`prune_outliers`) live on the model below. Wiring them to an actual optimiser, against
rendered images, is the separate piece of work.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import subprocess
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from standardphysics_pipeline.ingest import capture_to_room_from_payload
from standardphysics_pipeline.textures.scan_colour import scan_geometry


class StructuredGaussianModel(nn.Module):
    """3D Gaussian primitives with constrained scale ratios to prevent needles."""

    def __init__(self, init_points: np.ndarray, init_colors: np.ndarray | None = None):
        super().__init__()
        num_points = len(init_points)
        print(f"Initializing {num_points:,} Gaussians from LiDAR point cloud...")

        # Positions (means)
        self.positions = nn.Parameter(torch.from_numpy(init_points).float())

        # Log scales (isotropic initialization: ~2cm radius)
        init_log_scale = math.log(0.02)
        self.log_scales = nn.Parameter(torch.full((num_points, 3), init_log_scale, dtype=torch.float32))

        # Rotations as normalized quaternions (w, x, y, z)
        init_quats = np.zeros((num_points, 4), dtype=np.float32)
        init_quats[:, 0] = 1.0
        self.quats = nn.Parameter(torch.from_numpy(init_quats).float())

        # Opacities (inverse sigmoid)
        init_opacity = 0.5
        init_inv_sigmoid = math.log(init_opacity / (1.0 - init_opacity))
        self.inv_opacities = nn.Parameter(torch.full((num_points, 1), init_inv_sigmoid, dtype=torch.float32))

        # Colors as RGB spherical harmonics degree 0 (base color)
        if init_colors is not None:
            init_sh0 = (torch.from_numpy(init_colors).float() - 0.5) / 0.28209479177387814
        else:
            init_sh0 = torch.zeros((num_points, 3), dtype=torch.float32)
        self.sh0 = nn.Parameter(init_sh0)

    @property
    def scales(self) -> torch.Tensor:
        return torch.exp(self.log_scales)

    @property
    def opacities(self) -> torch.Tensor:
        return torch.sigmoid(self.inv_opacities)

    def scale_anisotropy_loss(self, max_ratio: float = 3.0) -> torch.Tensor:
        """Penalize Gaussians whose aspect ratio exceeds max_ratio.

        This directly stops needle-like elongation along camera rays.
        """
        scales = self.scales
        max_scale, _ = torch.max(scales, dim=1)
        min_scale, _ = torch.min(scales, dim=1)
        ratio = max_scale / (min_scale + 1e-6)
        penalty = F.relu(ratio - max_ratio)
        return penalty.mean()

    def prune_outliers(self, min_opacity: float = 0.05, max_scale: float = 0.15) -> int:
        """Prune low-opacity floaters and overly large Gaussians."""
        with torch.no_grad():
            scales = self.scales
            opacities = self.opacities.squeeze(1)
            max_s, _ = torch.max(scales, dim=1)

            keep_mask = (opacities >= min_opacity) & (max_s <= max_scale)
            num_pruned = int((~keep_mask).sum().item())

            if num_pruned > 0:
                self.positions = nn.Parameter(self.positions[keep_mask])
                self.log_scales = nn.Parameter(self.log_scales[keep_mask])
                self.quats = nn.Parameter(self.quats[keep_mask])
                self.inv_opacities = nn.Parameter(self.inv_opacities[keep_mask])
                self.sh0 = nn.Parameter(self.sh0[keep_mask])

            return num_pruned

    def export_ply(self, path: pathlib.Path):
        """Export as official 3DGS PLY format for compression to .spz."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with torch.no_grad():
            xyz = self.positions.cpu().numpy()
            scales = self.log_scales.cpu().numpy()
            quats = F.normalize(self.quats, dim=1).cpu().numpy()
            opacities = self.inv_opacities.cpu().numpy()
            sh = self.sh0.cpu().numpy()

        num_verts = len(xyz)
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
            # Pack vertex data: 3 pos + 3 sh + 1 opacity + 3 scale + 4 rot = 14 floats
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
            data["x"] = xyz[:, 0]
            data["y"] = xyz[:, 1]
            data["z"] = xyz[:, 2]
            data["f_dc_0"] = sh[:, 0]
            data["f_dc_1"] = sh[:, 1]
            data["f_dc_2"] = sh[:, 2]
            data["opacity"] = opacities[:, 0]
            data["scale_0"] = scales[:, 0]
            data["scale_1"] = scales[:, 1]
            data["scale_2"] = scales[:, 2]
            data["rot_0"] = quats[:, 0]
            data["rot_1"] = quats[:, 1]
            data["rot_2"] = quats[:, 2]
            data["rot_3"] = quats[:, 3]
            f.write(data.tobytes())
        print(f"Exported {num_verts:,} Gaussians to PLY: {path} ({path.stat().st_size / (1024*1024):.2f} MB)")


def room_frame_points(capture_dir: pathlib.Path, max_points: int, rng: np.random.Generator) -> np.ndarray:
    """LiDAR vertices in room coordinates, subsampled.

    Each anchor in the mesh carries its own transform and the capture carries a floor
    transform on top of that, so reading the raw vertex arrays piles every anchor on the
    origin. `scan_geometry` is what applies both, and is what the texture bake uses.
    """
    room = json.loads((capture_dir / "room.json").read_text())
    vertices, _ = scan_geometry(capture_dir / "lidar-mesh.json", capture_to_room_from_payload(room))
    print(f"Loaded {len(vertices):,} LiDAR vertices in room coordinates")
    if len(vertices) <= max_points:
        return vertices
    return vertices[rng.choice(len(vertices), max_points, replace=False)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=pathlib.Path, default=pathlib.Path("datasets/phone/moffett/454B3661-D3F8-46E8-ADAA-3123E759AA64"))
    parser.add_argument("--output-ply", type=pathlib.Path, default=pathlib.Path("runs/moffett/structured-splats/center.ply"))
    parser.add_argument("--output-spz", type=pathlib.Path, default=pathlib.Path("runs/moffett/structured-splats/center.spz"))
    parser.add_argument("--max-points", type=int, default=150_000)
    parser.add_argument("--seed", type=int, default=0, help="Fixes the subsample, so a rerun gives the same file.")
    args = parser.parse_args()

    t0 = time.time()
    print("=== Seeding Gaussians on the LiDAR surface ===")

    points = room_frame_points(args.capture_dir, args.max_points, np.random.default_rng(args.seed))
    model = StructuredGaussianModel(points)
    model.export_ply(args.output_ply)

    # The .spz is the artefact the viewer reads, so a missing or failing converter is a
    # failure of this script rather than a notice printed on the way to exit 0.
    converter = pathlib.Path("runs/moffett/tools/compress_moffett_splat")
    if not converter.is_file():
        raise FileNotFoundError(f"SPZ converter not built: {converter}")
    result = subprocess.run([str(converter), str(args.output_ply), str(args.output_spz)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"SPZ compression failed:\n{result.stderr}")
    print(f"Compressed to SPZ: {args.output_spz} ({args.output_spz.stat().st_size / (1024 * 1024):.2f} MB)")

    print(f"Completed in {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()
