"""Generate the materials that fill unphotographed walls, floors and labelled objects.

Two modes. Without --scan it makes the generic set that ships with the package. With
--scan it makes one room's own set: for every wall, floor and labelled object kind it
crops the photo that shows that surface best and asks the image model for a matching
repeating material, then writes them beside the scan, where the next texture build
picks them up. Either way a build reads the tiles from disk and never calls out.

Needs ELEVENLABS_API_KEY in the environment on a Pro plan or above, and spends image
credits for each material.

    .venv/bin/python scripts/generate_surface_materials.py
    .venv/bin/python scripts/generate_surface_materials.py --only wall
    .venv/bin/python scripts/generate_surface_materials.py --scan cdb7ced5-b67f-4f94-8639-0257a1dd8e9a
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import pathlib
import time
import uuid

import httpx
import numpy as np
from PIL import Image, ImageFilter
from standardphysics_pipeline.textures.material_references import ReferenceCrop, reference_crops
from standardphysics_pipeline.textures.scan_colour import coloured_scan, vertex_normals
from standardphysics_pipeline.textures.surface_materials import MANIFEST, MATERIALS_DIR, material_key, room_owners

from standardphysics_api.db import Database
from standardphysics_api.settings import Settings
from standardphysics_api.store import ArtifactStore
from standardphysics_api.textures import bake_inputs, room_materials_dir

API = "https://api.elevenlabs.io/v1/flows/image"
MODEL = "gpt-image-2"
TILE_PIXELS = 512
REFERENCE_EDGE = 1024
POLL_SECONDS = 2.0
MAX_POLL_SECONDS = 30.0
GIVE_UP_AFTER_SECONDS = 300.0

GENERIC = {
    "wall": {
        "prompt": (
            "A square close-up photograph of a matte painted interior wall, taken straight on so the "
            "wall fills the whole frame. Soft, even daylight. You can just see a fine paint roller "
            "stipple in the surface. A seamless texture swatch for a 3D material library."
        ),
        "metres_across": 1.0,
    },
    "floor": {
        "prompt": (
            "A square top-down photograph of a sealed polished concrete floor, taken straight down so "
            "the floor fills the whole frame. Soft, even overhead light. Gentle cloudy mottling and a "
            "fine aggregate grain. A seamless texture swatch for a 3D material library."
        ),
        "metres_across": 2.0,
    },
}
METRES_ACROSS = {"wall": 1.0, "floor": 2.0, "table": 1.0, "chair": 0.5, "television": 0.5, "outlet": 0.15}
DEFAULT_METRES_ACROSS = 0.5
SUBJECTS = {"wall": "the painted wall surface", "floor": "the floor covering"}


def _request(method: str, url: str, api_key: str, body: dict | None = None) -> dict:
    response = httpx.request(method, url, json=body, headers={"xi-api-key": api_key}, timeout=120)
    if response.is_error:
        raise SystemExit(f"ElevenLabs {method} {url} failed with {response.status_code}: {response.text[:500]}")
    return response.json()


def _finished(generation_id: str, api_key: str) -> dict:
    """Poll no faster than the documented two seconds, backing off, with a ceiling."""
    waited, interval = 0.0, POLL_SECONDS
    while waited < GIVE_UP_AFTER_SECONDS:
        time.sleep(interval)
        waited += interval
        result = _request("GET", f"{API}/{generation_id}", api_key)
        if result["status"] in ("completed", "failed"):
            return result
        interval = min(interval * 2, MAX_POLL_SECONDS)
    raise SystemExit(f"generation {generation_id} did not finish within {GIVE_UP_AFTER_SECONDS:.0f}s")


def _download(url: str) -> Image.Image:
    response = httpx.get(url, timeout=120, follow_redirects=True)
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content)).convert("RGB")


def _inline(image: Image.Image) -> dict:
    image = image.copy()
    image.thumbnail((REFERENCE_EDGE, REFERENCE_EDGE), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return {"type": "inline_base64", "content_base64": base64.b64encode(buffer.getvalue()).decode(), "mime_type": "image/jpeg"}


def evenly_lit(image: Image.Image) -> np.ndarray:
    """The image with its broad light falloff divided out, keeping only fine texture.

    A generated swatch is usually brighter on one side. Left in, that gradient
    turns into stripes once the tile is cross-faded and repeated.
    """
    pixels = np.asarray(image, dtype=np.float32)
    lighting = np.asarray(image.filter(ImageFilter.GaussianBlur(image.width / 8)), dtype=np.float32)
    return pixels / np.maximum(lighting, 1.0) * pixels.mean(axis=(0, 1))


def made_seamless(image: Image.Image, size: int = TILE_PIXELS) -> np.ndarray:
    """The image cross-faded with itself shifted half a tile, so opposite edges meet.

    The shifted copy's borders are the original's interior, which already runs
    continuously, so weighting it fully at the edges and the original fully at
    the centre leaves no seam where the tile repeats.
    """
    square = min(image.size)
    left, top = (image.width - square) // 2, (image.height - square) // 2
    pixels = evenly_lit(
        image.crop((left, top, left + square, top + square)).resize((size, size), Image.Resampling.LANCZOS)
    )
    shifted = np.roll(pixels, (size // 2, size // 2), axis=(0, 1))
    ramp = 1.0 - np.abs(np.linspace(-1.0, 1.0, size, dtype=np.float32))
    weight = np.minimum.outer(ramp, ramp)[..., None]
    return np.clip(pixels * weight + shifted * (1.0 - weight), 0, 255).astype(np.uint8)


def generate(key: str, prompt: str, metres_across: float, directory: pathlib.Path, api_key: str,
             reference: Image.Image | None = None) -> dict:
    """Generate one material, save it as <key>.png in directory, and return its manifest entry."""
    body = {"model_id": MODEL, "prompt": prompt, "aspect_ratio": "1:1", "resolution": "1K"}
    if reference is not None:
        body["images"] = [_inline(reference)]
    created = _request("POST", API, api_key, body)
    print(f"{key}: queued {created['id']}")
    result = _finished(created["id"], api_key)
    if result["status"] == "failed":
        raise SystemExit(f"{key}: {result.get('failure_reason')}: {result.get('error_message')}")
    Image.fromarray(made_seamless(_download(result["content_url"])), "RGB").save(directory / f"{key}.png", optimize=True)
    print(f"{key}: saved {directory / f'{key}.png'}")
    return {"image": f"{key}.png", "metres_across": metres_across, "model": MODEL, "prompt": prompt,
            "generation_id": created["id"]}


def room_prompt(key: str) -> str:
    subject = SUBJECTS.get(key, f"the main surface material of the {key}")
    return (
        f"The reference photo shows {subject} in a real room. Make a square, seamless, repeating texture "
        "swatch of exactly that material, as if photographed straight on so it fills the whole frame, in "
        "soft even light. Match its colour, pattern and grain. Show only the material itself, with no "
        "objects, edges, shadows or perspective."
    )


def _room_crops(scan_id: uuid.UUID) -> tuple[list[ReferenceCrop], pathlib.Path]:
    settings = Settings.from_environment()
    database = Database(settings.database_path)
    store = ArtifactStore(settings.data_dir, settings.max_artifact_bytes)
    graph, inputs = bake_inputs(database, store, scan_id)
    if inputs is None or not inputs["lidar"]:
        raise SystemExit("this scan has no photos or no LiDAR mesh to take references from")
    frame_paths = {frame: store.artifact_path(scan_id, artifact) for frame, artifact in inputs["frames"].items()}
    scan, cameras = coloured_scan(
        store.artifact_path(scan_id, inputs["lidar"]), store.artifact_path(scan_id, inputs["poses"]),
        frame_paths, graph.capture_to_room,
    )
    owners = room_owners(scan.vertices, vertex_normals(scan.vertices, scan.triangles), graph)
    keys = [material_key(node) for node in graph.nodes]
    return reference_crops(scan, owners, keys, cameras, frame_paths), room_materials_dir(store, scan_id)


def _write_manifest(directory: pathlib.Path, key: str, entry: dict) -> None:
    path = directory / MANIFEST
    manifest = json.loads(path.read_text()) if path.is_file() else {}
    manifest[key] = entry
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def generate_for_room(scan_id: uuid.UUID, only: list[str] | None, api_key: str) -> None:
    crops, directory = _room_crops(scan_id)
    directory.mkdir(parents=True, exist_ok=True)
    for crop in crops:
        if only and crop.key not in only:
            continue
        crop.image.save(directory / f"{crop.key}-reference.jpg", quality=90)
        print(f"{crop.key}: reference from {crop.frame_id} ({crop.points} photographed points)")
        entry = generate(crop.key, room_prompt(crop.key), METRES_ACROSS.get(crop.key, DEFAULT_METRES_ACROSS),
                         directory, api_key, reference=crop.image)
        _write_manifest(directory, crop.key, {**entry, "reference_frame": crop.frame_id, "tint": False})


def generate_generic(only: list[str] | None, api_key: str) -> None:
    MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
    for key in only or list(GENERIC):
        surface = GENERIC[key]
        _write_manifest(MATERIALS_DIR, key, generate(key, surface["prompt"], surface["metres_across"], MATERIALS_DIR, api_key))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scan", type=uuid.UUID, help="make this room's own materials from its photos")
    parser.add_argument("--only", action="append", help="a material key such as wall, floor or chair")
    args = parser.parse_args()
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise SystemExit("ELEVENLABS_API_KEY is not set")
    if args.scan:
        generate_for_room(args.scan, args.only, api_key)
    else:
        generate_generic(args.only, api_key)


if __name__ == "__main__":
    main()
