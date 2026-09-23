"""Display-only SPAR3D trial on room 6's most photographed chair and suspect sofa.

    .venv/bin/python scripts/spar3d_furniture_experiment.py --prepare-only
    .venv/bin/python scripts/spar3d_furniture_experiment.py

The sofa is recorded but not reconstructed: its measured box describes only a
small fragment, and its source crop does not show a whole sofa.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import uuid
from dataclasses import dataclass

import numpy as np
import trimesh
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, gaussian_filter
from standardphysics_contracts import SceneGraph
from standardphysics_pipeline.check_blender import blender_path
from standardphysics_pipeline.discovery.discover import known_detections
from standardphysics_pipeline.textures.camera import PhotoCamera
from standardphysics_pipeline.textures.furniture_experiment import (
    FurnitureEvidence,
    box_iou,
    choose_yaw,
    furniture_evidence,
    spar_point_cloud,
)
from standardphysics_pipeline.textures.object_holes import people_masks
from standardphysics_pipeline.textures.project import depth_buffer
from standardphysics_pipeline.textures.scan_colour import (
    ColouredScan,
    colour_the_scan,
    coloured_scan,
    unused_vertices_removed,
    vertex_normals,
    write_scan_glb,
)
from standardphysics_pipeline.textures.surface_materials import room_owners

from standardphysics_api.db import Database
from standardphysics_api.settings import Settings
from standardphysics_api.store import ArtifactStore
from standardphysics_api.textures import bake_inputs, room_detections_dir

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/spar3d-experiment"
SOURCE = RUN / "source"
SPAR_PYTHON = pathlib.Path.home() / ".venvs/spar3d/bin/python"
SCAN_ID = uuid.UUID("cdb7ced5-b67f-4f94-8639-0257a1dd8e9a")
CHAIR_FRAME = "frame-0089"
HOLDOUT_FRAMES = ("frame-0086", "frame-0087", "frame-0091", "frame-0092", "frame-0094")
RENDER_SIZE = (960, 720)


@dataclass(frozen=True)
class RoomEvidence:
    graph: SceneGraph
    scan: ColouredScan
    owners: np.ndarray
    cameras: list[PhotoCamera]
    frame_paths: dict[str, pathlib.Path]
    people: dict


def room_evidence() -> RoomEvidence:
    settings = Settings.from_environment()
    database = Database(settings.database_path)
    store = ArtifactStore(settings.data_dir, settings.max_artifact_bytes)
    graph, inputs = bake_inputs(database, store, SCAN_ID)
    if inputs is None or not inputs.get("lidar"):
        raise RuntimeError("room 6 needs photos and a LiDAR mesh")
    frame_paths = {frame: store.artifact_path(SCAN_ID, artifact) for frame, artifact in inputs["frames"].items()}
    poses = store.artifact_path(SCAN_ID, inputs["poses"])
    people = known_detections(frame_paths, poses, room_detections_dir(store, SCAN_ID))
    scan, cameras = coloured_scan(
        store.artifact_path(SCAN_ID, inputs["lidar"]), poses, frame_paths,
        graph.capture_to_room, patch_holes_from=graph, people=people,
    )
    owners = room_owners(scan.vertices, vertex_normals(scan.vertices, scan.triangles), graph, patches=scan.sheet_patches)
    return RoomEvidence(graph, scan, owners, cameras, frame_paths, people)


def selected_node(room: RoomEvidence, label: str) -> int:
    indices = [index for index, node in enumerate(room.graph.nodes) if node.label.lower() == label]
    if not indices:
        raise RuntimeError(f"room 6 has no {label}")
    return max(indices, key=lambda index: int(((room.owners == index) & room.scan.scanned & room.scan.seen).sum()))


def save_input(evidence: FurnitureEvidence, camera, output: pathlib.Path) -> None:
    if evidence.crop is None:
        raise ValueError("no photographed crop for this object")
    centre = evidence.box.centre[None, :]
    u, v, _ = camera.project(np.vstack((centre, centre + [0, 0, 0.2])))
    angle = float(np.degrees(np.arctan2(u[1] - u[0], -(v[1] - v[0]))))
    evidence.crop.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC).save(output)


def save_lidar_object(room: RoomEvidence, node_index: int, output: pathlib.Path) -> pathlib.Path:
    triangles = room.scan.triangles
    selected = ((room.owners[triangles] == node_index) & room.scan.scanned[triangles]).all(axis=1)
    if not selected.any():
        raise ValueError("the object has no measured LiDAR triangles")
    object_scan = ColouredScan(
        room.scan.vertices, triangles[selected], room.scan.colours, room.scan.seen,
        sources=room.scan.sources, inferred=room.scan.inferred,
    )
    return write_scan_glb(unused_vertices_removed(object_scan), output)


def prepare_object(room: RoomEvidence, node_index: int, name: str, reviewed_frame: str | None = None) -> tuple[FurnitureEvidence, dict]:
    directory = RUN / name
    directory.mkdir(parents=True, exist_ok=True)
    evidence = furniture_evidence(
        room.scan, room.owners, room.graph, node_index, room.cameras,
        room.frame_paths, room.people, reviewed_frame_id=reviewed_frame,
    )
    node = room.graph.nodes[node_index]
    record = {
        "node_id": str(node.id), "label": node.label,
        "box_metres": evidence.box.dimensions.tolist(),
        "scanned_points": len(evidence.points_local),
        "photographed_points": evidence.photographed_points,
        "input_frame": evidence.crop_frame_id,
    }
    if evidence.crop is None:
        record.update(status="skipped", reason="No crop passes the photographed-point threshold; the box is only a fragment")
        return evidence, record
    camera = next(camera for camera in room.cameras if camera.frame_id == evidence.crop_frame_id)
    save_input(evidence, camera, directory / "input.png")
    np.save(directory / "pointcloud.npy", spar_point_cloud(evidence.points_local, evidence.colours, evidence.box, camera))
    save_lidar_object(room, node_index, directory / "lidar.glb")
    record["status"] = "prepared"
    return evidence, record


def infer(directory: pathlib.Path) -> dict:
    if not SPAR_PYTHON.is_file() or not (SOURCE / "spar3d/system.py").is_file():
        raise RuntimeError("SPAR3D source or its isolated virtualenv is missing")
    environment = {
        **os.environ, "PYTORCH_ENABLE_MPS_FALLBACK": "1",
        "PYTHONPATH": str(SOURCE) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    command = [
        str(SPAR_PYTHON), str(ROOT / "scripts/spar3d_infer.py"),
        "--image", str(directory / "input.png"), "--cloud", str(directory / "pointcloud.npy"),
        "--out", str(directory / "raw.glb"),
    ]
    result = subprocess.run(command, cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=2400)
    (directory / "inference.log").write_text(result.stdout + "\n" + result.stderr)
    if result.returncode:
        raise RuntimeError(f"SPAR3D inference failed; see {directory / 'inference.log'}")
    return json.loads((directory / "inference.json").read_text())


def weights_available() -> bool:
    command = [
        str(SPAR_PYTHON), "-c",
        "from huggingface_hub import hf_hub_download; "
        "hf_hub_download('stabilityai/stable-point-aware-3d', 'config.yaml')",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    return result.returncode == 0


def heldout_cameras(room: RoomEvidence, input_frame: str) -> list:
    by_frame = {camera.frame_id: camera for camera in room.cameras}
    frames = [frame for frame in HOLDOUT_FRAMES if frame != input_frame and frame in by_frame]
    if len(frames) < 5:
        raise RuntimeError("at least five distinct held-out calibrated photos are required")
    return [by_frame[frame] for frame in frames]


def training_photos(room: RoomEvidence, exclude: set[str]) -> tuple[list, list[np.ndarray], list[np.ndarray]]:
    cameras = [camera for camera in room.cameras if camera.frame_id not in exclude]
    picks = np.linspace(0, len(cameras) - 1, min(40, len(cameras))).round().astype(int)
    cameras = [cameras[index] for index in dict.fromkeys(picks.tolist())]
    images, resized = [], []
    for camera in cameras:
        with Image.open(room.frame_paths[camera.frame_id]) as opened:
            photo = opened.convert("RGB")
            photo.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            image = np.asarray(photo, dtype=np.float32) / 255.0
        images.append(image)
        resized.append(camera.resized(image.shape[1], image.shape[0]))
    shapes = {camera.frame_id: image.shape[:2] for camera, image in zip(cameras, images)}
    masks = people_masks(room.people, cameras, shapes)
    return resized, images, [masks[camera.frame_id] for camera in resized]


def hidden_by_room(camera: PhotoCamera, vertices: np.ndarray, room_depth: np.ndarray) -> np.ndarray:
    columns, rows, depth = camera.project(vertices)
    height, width = room_depth.shape
    columns = np.clip(np.rint(columns * width / camera.width).astype(np.int64), 0, width - 1)
    rows = np.clip(np.rint(rows * height / camera.height).astype(np.int64), 0, height - 1)
    return depth > room_depth[rows, columns] + 0.05


def fitted_mesh(room: RoomEvidence, evidence: FurnitureEvidence, node_index: int, directory: pathlib.Path) -> dict:
    raw = trimesh.load(directory / "raw.glb", force="mesh")
    if not isinstance(raw, trimesh.Trimesh):
        raise ValueError("SPAR3D output is not a triangle mesh")
    if evidence.crop_frame_id is None:
        raise ValueError("the fitted object has no input photo")
    z_up = np.column_stack((raw.vertices[:, 0], -raw.vertices[:, 2], raw.vertices[:, 1]))
    fitted, yaw, distance = choose_yaw(z_up, raw.faces, evidence.box.dimensions, evidence.points_local)
    world = evidence.box.to_room(fitted)
    heldout = heldout_cameras(room, evidence.crop_frame_id)
    excluded = {evidence.crop_frame_id, *(camera.frame_id for camera in heldout)}
    cameras, images, masks = training_photos(room, excluded)
    other_points = room.scan.vertices[(room.owners != node_index) & room.scan.scanned]
    room_depth = {camera.frame_id: depth_buffer(camera, other_points) for camera in cameras}
    painted = colour_the_scan(
        world, raw.faces, cameras, images, masks=masks,
        hidden=lambda camera: hidden_by_room(camera, world, room_depth[camera.frame_id]),
    )
    write_scan_glb(painted, directory / "fitted.glb")
    return {
        "yaw_degrees": yaw * 90,
        "box_iou": box_iou(fitted, evidence.box.dimensions),
        "box_iou_pass": box_iou(fitted, evidence.box.dimensions) >= 0.85,
        "lidar_to_surface_cm": distance * 100,
        "texture_photos": len(cameras),
        "texture_painted_fraction": painted.painted_fraction,
    }


def render_pair(directory: pathlib.Path, camera, centre: np.ndarray) -> tuple[pathlib.Path, pathlib.Path]:
    views = directory / "views"
    views.mkdir(exist_ok=True)
    scaled = camera.resized(*RENDER_SIZE)
    config = {
        "width": scaled.width, "height": scaled.height,
        "fx": scaled.fx, "fy": scaled.fy, "cx": scaled.cx, "cy": scaled.cy,
        "room_to_camera": scaled.room_to_camera.tolist(), "box_centre": centre.tolist(),
    }
    config_path = views / f"{camera.frame_id}.json"
    config_path.write_text(json.dumps(config))
    lidar_path = views / f"{camera.frame_id}-lidar.png"
    fitted_path = views / f"{camera.frame_id}-spar3d.png"
    command = [
        blender_path(), "--background", "--python", str(ROOT / "scripts/spar3d_render.py"), "--",
        "--config", str(config_path), "--lidar", str(directory / "lidar.glb"),
        "--fitted", str(directory / "fitted.glb"), "--lidar-out", str(lidar_path),
        "--fitted-out", str(fitted_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode or "POSE_RENDERS_WRITTEN" not in result.stdout:
        raise RuntimeError(f"Blender pose render failed:\n{(result.stdout + result.stderr)[-1800:]}")
    return lidar_path, fitted_path


def _ssim_map(reference: np.ndarray, rendered: np.ndarray) -> np.ndarray:
    """Local SSIM with the usual 11-pixel Gaussian window and unit RGB range."""
    mean_a = gaussian_filter(reference, (1.5, 1.5, 0))
    mean_b = gaussian_filter(rendered, (1.5, 1.5, 0))
    var_a = gaussian_filter(reference * reference, (1.5, 1.5, 0)) - mean_a ** 2
    var_b = gaussian_filter(rendered * rendered, (1.5, 1.5, 0)) - mean_b ** 2
    covariance = gaussian_filter(reference * rendered, (1.5, 1.5, 0)) - mean_a * mean_b
    numerator = (2 * mean_a * mean_b + 0.01 ** 2) * (2 * covariance + 0.03 ** 2)
    denominator = (mean_a ** 2 + mean_b ** 2 + 0.01 ** 2) * (var_a + var_b + 0.03 ** 2)
    return (numerator / np.maximum(denominator, 1e-9)).mean(axis=2)


def compare_view(room: RoomEvidence, camera, lidar_path: pathlib.Path, fitted_path: pathlib.Path) -> dict:
    with Image.open(room.frame_paths[camera.frame_id]) as opened:
        photo = np.asarray(opened.convert("RGB").resize(RENDER_SIZE), dtype=np.float32) / 255
    lidar = np.asarray(Image.open(lidar_path).convert("RGBA"), dtype=np.float32) / 255
    fitted = np.asarray(Image.open(fitted_path).convert("RGBA"), dtype=np.float32) / 255
    mask = np.asarray(binary_dilation((lidar[:, :, 3] > 0.2) | (fitted[:, :, 3] > 0.2), iterations=3), dtype=bool)
    static = people_masks(room.people, [camera], {camera.frame_id: (RENDER_SIZE[1], RENDER_SIZE[0])})
    mask = mask & (static[camera.frame_id] > 0.5)
    if mask.sum() < 100:
        raise RuntimeError(f"{camera.frame_id} has too few unmasked object pixels to score")
    neutral = np.full_like(photo, 0.5)
    lidar_rgb = lidar[:, :, :3] * lidar[:, :, 3:] + neutral * (1 - lidar[:, :, 3:])
    fitted_rgb = fitted[:, :, :3] * fitted[:, :, 3:] + neutral * (1 - fitted[:, :, 3:])
    original = np.where(mask[:, :, None], photo, neutral)
    lidar_rgb = np.where(mask[:, :, None], lidar_rgb, neutral)
    fitted_rgb = np.where(mask[:, :, None], fitted_rgb, neutral)
    lidar_score = float(_ssim_map(original, lidar_rgb)[mask].mean())
    fitted_score = float(_ssim_map(original, fitted_rgb)[mask].mean())
    comparison = comparison_image(original, lidar_rgb, fitted_rgb, mask)
    output = fitted_path.with_name(f"{camera.frame_id}-comparison.jpg")
    comparison.save(output, quality=90)
    return {
        "frame": camera.frame_id, "pixels": int(mask.sum()),
        "lidar_ssim": lidar_score, "spar3d_ssim": fitted_score,
        "comparison": str(output.relative_to(ROOT)),
    }


def comparison_image(photo: np.ndarray, lidar: np.ndarray, fitted: np.ndarray, mask: np.ndarray) -> Image.Image:
    rows, columns = np.nonzero(mask)
    top, bottom = max(0, rows.min() - 20), min(mask.shape[0], rows.max() + 21)
    left, right = max(0, columns.min() - 20), min(mask.shape[1], columns.max() + 21)
    panels = [Image.fromarray((image[top:bottom, left:right] * 255).astype(np.uint8)) for image in (photo, lidar, fitted)]
    width, height = panels[0].size
    sheet = Image.new("RGB", (width * 3, height + 28), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (panel, label) in enumerate(zip(panels, ("Photo", "LiDAR", "SPAR3D"))):
        sheet.paste(panel, (index * width, 28))
        draw.text((index * width + 8, 8), label, fill="black")
    return sheet


def evaluate_views(room: RoomEvidence, evidence: FurnitureEvidence, directory: pathlib.Path) -> dict:
    if evidence.crop_frame_id is None:
        raise ValueError("the fitted object has no input photo")
    views = []
    for camera in heldout_cameras(room, evidence.crop_frame_id):
        lidar_path, fitted_path = render_pair(directory, camera, evidence.box.centre)
        views.append(compare_view(room, camera, lidar_path, fitted_path))
    return {"views": views, "photo_ssim_mean": float(np.mean([view["spar3d_ssim"] for view in views]))}


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--prepare-only", action="store_true", help="write scan evidence without loading gated weights")
    args = parser.parse_args()
    RUN.mkdir(parents=True, exist_ok=True)
    room = room_evidence()
    chair_index, sofa_index = selected_node(room, "chair"), selected_node(room, "sofa")
    chair, chair_record = prepare_object(room, chair_index, "chair", reviewed_frame=CHAIR_FRAME)
    sofa, sofa_record = prepare_object(room, sofa_index, "sofa")
    results = {"scan_id": str(SCAN_ID), "chair": chair_record, "sofa": sofa_record}
    if args.prepare_only:
        (RUN / "metrics.json").write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(results, indent=2))
        return
    if sofa.crop is not None:
        raise RuntimeError("sofa crop needs visual confirmation before model inference")
    if not weights_available():
        chair_record.update(status="blocked", reason="Hugging Face has not approved access to SPAR3D weights")
        (RUN / "metrics.json").write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(results, indent=2))
        return
    try:
        chair_record.update(infer(RUN / "chair"))
        chair_record.update(fitted_mesh(room, chair, chair_index, RUN / "chair"))
        chair_record.update(evaluate_views(room, chair, RUN / "chair"))
        chair_record["status"] = "complete"
    except Exception as error:
        chair_record.update(status="failed", error=str(error))
        raise
    finally:
        (RUN / "metrics.json").write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
