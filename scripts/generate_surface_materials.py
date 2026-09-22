"""Generate the wall and floor tiles that fill unphotographed room surfaces.

Run once, then commit the tiles: a texture build reads them from disk and never calls
out, so a bake stays offline, repeatable and free. Needs ELEVENLABS_API_KEY in the
environment on a Pro plan or above, and spends image credits for each surface.

    .venv/bin/python scripts/generate_surface_materials.py            # every surface
    .venv/bin/python scripts/generate_surface_materials.py --only wall
"""
from __future__ import annotations

import argparse
import io
import json
import os
import time

import httpx
import numpy as np
from PIL import Image, ImageFilter
from standardphysics_pipeline.textures.surface_materials import MANIFEST, MATERIALS_DIR, SURFACE_KINDS

API = "https://api.elevenlabs.io/v1/flows/image"
MODEL = "gpt-image-2"
TILE_PIXELS = 512
POLL_SECONDS = 2.0
MAX_POLL_SECONDS = 30.0
GIVE_UP_AFTER_SECONDS = 300.0

SURFACES = {
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


def _request(method: str, url: str, api_key: str, body: dict | None = None) -> dict:
    response = httpx.request(method, url, json=body, headers={"xi-api-key": api_key}, timeout=60)
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


def generate(kind: str, api_key: str) -> dict:
    surface = SURFACES[kind]
    created = _request("POST", API, api_key, {
        "model_id": MODEL, "prompt": surface["prompt"], "aspect_ratio": "1:1", "resolution": "1K",
    })
    print(f"{kind}: queued {created['id']}")
    result = _finished(created["id"], api_key)
    if result["status"] == "failed":
        raise SystemExit(f"{kind}: {result.get('failure_reason')}: {result.get('error_message')}")
    tile = made_seamless(_download(result["content_url"]))
    Image.fromarray(tile, "RGB").save(MATERIALS_DIR / f"{kind}.png", optimize=True)
    print(f"{kind}: saved {MATERIALS_DIR / f'{kind}.png'}")
    return {
        "image": f"{kind}.png", "metres_across": surface["metres_across"],
        "model": MODEL, "prompt": surface["prompt"], "generation_id": created["id"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=SURFACE_KINDS, action="append")
    args = parser.parse_args()
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise SystemExit("ELEVENLABS_API_KEY is not set")
    MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = MATERIALS_DIR / MANIFEST
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    for kind in args.only or SURFACE_KINDS:
        manifest[kind] = generate(kind, api_key)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
