"""Train/predict Gaussian splats using Google DeepFusion (LearnableAlign + InverseAug).

Fuses metric LiDAR point clouds with calibrated video keyframes to predict structured
3D Gaussian splat parameters (positions, scales, rotations, opacities, and SH0 colors)
in seconds without 30k-step gradient descent.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import subprocess
import time

import numpy as np
from PIL import Image
import torch

from standardphysics_pipeline.ingest import capture_to_room_from_payload
from standardphysics_pipeline.splats.deep_gaussian_model import DeepFusionGaussianModel
from standardphysics_pipeline.textures.camera import PhotoCamera, load_cameras
from standardphysics_pipeline.textures.scan_colour import scan_geometry


def load_room_geometry(capture_dir: pathlib.Path, max_points: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Load LiDAR vertices and compute approximate surface normals."""
    room_payload = json.loads((capture_dir / "room.json").read_text())
    room = capture_to_room_from_payload(room_payload)
    vertices, triangles = scan_geometry(capture_dir / "lidar-mesh.json", room)

    print(f"Loaded {len(vertices):,} LiDAR vertices and {len(triangles):,} triangles")

    # Compute vertex normals from triangles
    normals = np.zeros_like(vertices)
    v0 = vertices[triangles[:, 0]]
    v1 = vertices[triangles[:, 1]]
    v2 = vertices[triangles[:, 2]]
    face_normals = np.cross(v1 - v0, v2 - v0)
    # Normalize face normals
    face_lens = np.linalg.norm(face_normals, axis=-1, keepdims=True)
    face_normals = np.divide(face_normals, face_lens, out=np.zeros_like(face_normals), where=face_lens > 1e-8)

    for i in range(3):
        np.add.at(normals, triangles[:, i], face_normals)

    norm_lens = np.linalg.norm(normals, axis=-1, keepdims=True)
    normals = np.divide(normals, norm_lens, out=np.zeros_like(normals), where=norm_lens > 1e-8)
    # Default unoriented to +Z
    zero_mask = (norm_lens.squeeze(-1) < 1e-8)
    normals[zero_mask] = np.array([0.0, 0.0, 1.0])

    if len(vertices) > max_points:
        chosen = rng.choice(len(vertices), max_points, replace=False)
        vertices = vertices[chosen]
        normals = normals[chosen]

    return vertices, normals


def load_keyframes_and_cameras(
    capture_dir: pathlib.Path,
    max_cameras: int = 40,
    target_width: int = 640,
) -> tuple[list[PhotoCamera], list[np.ndarray]]:
    """Load calibrated camera poses and corresponding downscaled RGB images."""
    poses_path = capture_dir / "poses.json"
    frames_dir = capture_dir / "frames"

    if not poses_path.is_file() or not frames_dir.is_dir():
        print("Warning: poses.json or frames/ not found; proceeding with empty camera set")
        return [], []

    # Get available frame files
    frame_files = sorted(frames_dir.glob("frame_*.jpg"))
    if not frame_files:
        frame_files = sorted(frames_dir.glob("*.jpg"))

    frame_ids = [f.stem.replace("_", "-") for f in frame_files]

    room_payload = json.loads((capture_dir / "room.json").read_text())
    room = capture_to_room_from_payload(room_payload)

    try:
        all_cameras = load_cameras(poses_path, frame_ids, room)
    except Exception as e:
        print(f"Warning loading cameras: {e}")
        return [], []

    if not all_cameras:
        return [], []

    # Subsample cameras evenly across the walk
    stride = max(1, len(all_cameras) // max_cameras)
    selected_cameras = all_cameras[::stride][:max_cameras]

    images = []
    final_cameras = []

    for cam in selected_cameras:
        # Match frame file: frame-0001 -> frame_0001.jpg
        cand_name = cam.frame_id.replace("-", "_") + ".jpg"
        img_path = frames_dir / cand_name
        if not img_path.is_file():
            img_path = frames_dir / f"{cam.frame_id}.jpg"
        if not img_path.is_file():
            continue

        with Image.open(img_path) as im:
            im = im.convert("RGB")
            orig_w, orig_h = im.size
            scale = target_width / orig_w
            target_height = int(orig_h * scale)
            im_resized = im.resize((target_width, target_height), Image.Resampling.BILINEAR)
            img_np = np.asarray(im_resized)

        # Scale camera intrinsics
        scaled_cam = cam.resized(target_width, target_height)
        final_cameras.append(scaled_cam)
        images.append(img_np)

    print(f"Loaded {len(final_cameras)} calibrated cameras and keyframe images")
    return final_cameras, images


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=pathlib.Path, default=pathlib.Path("datasets/phone/moffett/454B3661-D3F8-46E8-ADAA-3123E759AA64"))
    parser.add_argument("--output-ply", type=pathlib.Path, default=pathlib.Path("runs/moffett/deepfusion-splats/center.ply"))
    parser.add_argument("--output-spz", type=pathlib.Path, default=pathlib.Path("runs/moffett/deepfusion-splats/center.spz"))
    parser.add_argument("--max-points", type=int, default=150_000)
    parser.add_argument("--max-cameras", type=int, default=32)
    parser.add_argument("--target-width", type=int, default=480)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-spz", action="store_true")
    args = parser.parse_args()

    t0 = time.time()
    print("=== DeepFusion LiDAR-Camera Gaussian Splatting ===")
    rng = np.random.default_rng(args.seed)

    # 1. Load geometry and cameras
    vertices, normals = load_room_geometry(args.capture_dir, args.max_points, rng)
    cameras, images = load_keyframes_and_cameras(args.capture_dir, args.max_cameras, args.target_width)

    # 2. Select device (MPS if available, else CPU)
    if torch.backends.mps.is_available():
        device = torch.device("mps")
        print("Using Apple Silicon Metal (MPS) acceleration")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
        print("Using CUDA acceleration")
    else:
        device = torch.device("cpu")
        print("Using CPU")

    # 3. Instantiate model
    model = DeepFusionGaussianModel(
        point_dim=64,
        image_dim=64,
        hidden_dim=64,
        base_log_scale=math.log(0.02),
        max_position_offset_m=0.03,
    ).to(device)

    # 4. Predict Gaussian splats
    t_pred = time.time()
    print(f"Predicting Gaussian splat parameters for {len(vertices):,} points across {len(cameras)} cameras...")
    prediction = model.predict_splats(vertices, normals, cameras, images)
    pred_duration = time.time() - t_pred
    print(f"Prediction complete in {pred_duration:.2f}s")

    # 5. Export PLY
    args.output_ply.parent.mkdir(parents=True, exist_ok=True)
    prediction.export_ply(args.output_ply)
    print(f"Exported PLY: {args.output_ply} ({args.output_ply.stat().st_size / (1024 * 1024):.2f} MB)")

    # 6. Compress to SPZ if converter exists and not skipped
    converter = pathlib.Path("runs/moffett/tools/compress_moffett_splat")
    if not args.skip_spz and converter.is_file():
        result = subprocess.run([str(converter), str(args.output_ply), str(args.output_spz)], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Compressed to SPZ: {args.output_spz} ({args.output_spz.stat().st_size / (1024 * 1024):.2f} MB)")
        else:
            print(f"SPZ compression warning:\n{result.stderr}")

    total_duration = time.time() - t0
    print(f"Total DeepFusion pipeline completed in {total_duration:.2f}s")


if __name__ == "__main__":
    main()
