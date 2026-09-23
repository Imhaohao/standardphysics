"""Run one isolated SPAR3D inference in ~/.venvs/spar3d, outside the project venv."""

from __future__ import annotations

import argparse
import json
import pathlib
import resource
import sys
import time
from typing import cast

import numpy as np
import torch
import trimesh
from PIL import Image, ImageChops
from spar3d.system import SPAR3D
from spar3d.utils import foreground_crop, get_device, remove_background
from transparent_background import Remover


def prepared_image(path: pathlib.Path, device: str) -> Image.Image:
    """Remove the room background while retaining the people-mask transparency."""
    with Image.open(path) as opened:
        photo = opened.convert("RGBA")
    cutout = cast(
        Image.Image,
        remove_background(photo.convert("RGB").convert("RGBA"), Remover(device=device), force=True),  # pyright: ignore[reportArgumentType]
    )
    cutout.putalpha(ImageChops.multiply(cutout.getchannel("A"), photo.getchannel("A")))
    return cast(Image.Image, foreground_crop(cutout, 1.3))


def run(image_path: pathlib.Path, cloud_path: pathlib.Path, output: pathlib.Path) -> dict:
    device = get_device()
    if device != "mps":
        raise RuntimeError(f"SPAR3D experiment requires MPS; detected {device}")
    pointcloud = np.load(cloud_path).astype(np.float32)
    if pointcloud.shape != (512, 6):
        raise ValueError("SPAR3D point cloud must be a 512 x 6 XYZRGB array")
    image = prepared_image(image_path, device)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output.with_name("prepared-input.png"))
    started = time.monotonic()
    model = SPAR3D.from_pretrained(
        "stabilityai/stable-point-aware-3d", config_name="config.yaml", weight_name="model.safetensors",
    ).to(device)
    model.eval()
    with torch.no_grad():
        mesh, _ = model.run_image(image, bake_resolution=512, pointcloud=pointcloud)
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError("SPAR3D returned no single-object mesh")
    torch.mps.synchronize()
    elapsed = time.monotonic() - started
    mesh.export(output, include_normals=True)
    return {
        "device": device,
        "seconds": round(elapsed, 2),
        "peak_process_memory_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 3, 3),
        "mps_driver_memory_gb_at_end": round(torch.mps.driver_allocated_memory() / 1024 ** 3, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=pathlib.Path, required=True)
    parser.add_argument("--cloud", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    metrics = run(args.image, args.cloud, args.out)
    args.out.with_name("inference.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics))


if __name__ == "__main__":
    sys.exit(main())
