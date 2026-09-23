"""The painted scan as photographs laid over its surface, rather than one colour per vertex.

A vertex-coloured scan is only as sharp as its vertices are close together, and
once it is thinned for the viewer they sit ten to fifteen centimetres apart, so
a shelf of books reads as a smear. Here the thinned mesh is unwrapped and every
texel, about two centimetres of surface, is coloured from the photographs.

Every photo of the walk is read, not an evenly spaced sixty. More photos mean a
closer, squarer view of each patch of surface and fewer patches nobody saw.
They are read one at a time and let go, twice: once to even out exposure between
them and once to bake, so memory stays flat however long the walk was.

Occlusion is judged against the unwrapped surface itself, sampled texel by
texel, so a surface the thinning moved a few centimetres is not hidden by the
full-resolution scan it no longer quite lies on.

A texel no photo reached takes the colour the vertex painting gave that stretch
of surface, which is itself a photograph or the room's generated material.
"""

from __future__ import annotations

import pathlib
import tempfile
import time
from dataclasses import dataclass

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from standardphysics_contracts import SceneGraph

from .camera import PhotoCamera
from .hole_patches import hidden_behind_objects
from .object_holes import people_masks
from .project import (
    MAX_EXPOSURE_POINTS,
    TopViews,
    bilinear,
    depth_buffer,
    exposure_gains,
    face_normals,
    pad_gutters,
    rasterize_atlas,
    to_linear,
    to_srgb,
)
from .scan_colour import BLEND_SHARPNESS, ColouredScan, _small_static_mask, _weights_from

TEXEL_METRES = 0.02
MIN_ATLAS_SIZE = 512
MAX_ATLAS_SIZE = 4096
MAX_ATLAS_PHOTOS = 800
"""Photos read per walk. Neighbouring video frames are nearly the same view, so past this they add time and little else."""
PHOTO_EDGE = 1600
EXPOSURE_PHOTO_EDGE = 400
"""Exposure is a per-photo brightness, so it can be read off a thumbnail."""
BLOCK_METRES = 1.0
"""The size of the cubes texels are grouped into, so a photo only projects the texels it could see."""
ATLAS_JPEG_QUALITY = 90
CONSENSUS_VIEWS = 5
"""How many of the best views each texel keeps, so the colour most of them agree on can win."""
FALLBACK_NEIGHBOURS = 8
AGREEMENT_DISTANCE = 0.06
"""How close two linear colours are to count as the same surface seen twice."""


@dataclass(frozen=True)
class UnwrappedScan:
    vertices: np.ndarray
    triangles: np.ndarray
    uv: np.ndarray
    """A UV pair for each corner of each triangle, shape (triangles, 3, 2)."""

    @property
    def corners(self) -> np.ndarray:
        return self.vertices[self.triangles]


@dataclass(frozen=True)
class AtlasPaint:
    glb_path: pathlib.Path
    painted_fraction: float
    """The share of texels a photo coloured, before any fill."""
    photos_used: int
    atlas_size: int
    seconds: float


def unwrapped(scan: ColouredScan, work: pathlib.Path, max_triangles: int) -> UnwrappedScan:
    """The scan thinned for the viewer and unwrapped by Blender."""
    from ..blender import _run

    source, result = work / "scan.npz", work / "unwrapped.npz"
    np.savez(source, vertices=scan.vertices.astype(np.float32), triangles=scan.triangles.astype(np.int32))
    output = _run("unwrap_scan.py", ["--scan", str(source), "--out", str(result), "--max-triangles", str(max_triangles)])
    if "SCAN_UNWRAPPED" not in output:
        raise RuntimeError(f"Blender did not unwrap the scan:\n{output[-1500:]}")
    archive = np.load(result)
    return UnwrappedScan(archive["vertices"], archive["triangles"], archive["uv"])


def atlas_size(mesh: UnwrappedScan) -> int:
    """The smallest power-of-two side that gives each texel about TEXEL_METRES of surface."""
    _, world_areas = face_normals(mesh.corners)
    uv = mesh.uv
    first, second = uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]
    uv_areas = np.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]) / 2
    needed = world_areas.sum() / TEXEL_METRES ** 2 / max(uv_areas.sum(), 1e-9)
    side = 2 ** int(np.ceil(np.log2(max(np.sqrt(needed), 1.0))))
    return int(np.clip(side, MIN_ATLAS_SIZE, MAX_ATLAS_SIZE))


class _Blocks:
    """Texels grouped into cubes, so each photo projects only the cubes inside its frame."""

    def __init__(self, points: np.ndarray):
        keys = np.floor(points / BLOCK_METRES).astype(np.int64)
        unique, inverse = np.unique(keys, axis=0, return_inverse=True)
        self.order = np.argsort(inverse.ravel(), kind="stable")
        self.starts = np.searchsorted(inverse.ravel()[self.order], np.arange(len(unique) + 1))
        self.centres = (unique + 0.5) * BLOCK_METRES
        self.radius = BLOCK_METRES * np.sqrt(3) / 2

    def seen_by(self, camera: PhotoCamera) -> np.ndarray:
        """Indices of every texel in a cube that reaches into the camera's frame."""
        u, v, depth = camera.project(self.centres)
        reach = self.radius * max(camera.fx, camera.fy) / np.maximum(depth, 0.1)
        near = depth < self.radius
        framed = (depth > -self.radius) & (u > -reach) & (u < camera.width + reach) & (v > -reach) & (v < camera.height + reach)
        chosen = np.flatnonzero(near | framed)
        first, count = self.starts[chosen], self.starts[chosen + 1] - self.starts[chosen]
        offsets = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
        return self.order[np.repeat(first, count) + offsets]


def _read(path: pathlib.Path, edge: int) -> np.ndarray:
    with Image.open(path) as opened:
        image = opened.convert("RGB")
        image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
        return np.asarray(image, dtype=np.float32) / 255.0


class _Surface:
    """The texels of one atlas and what the photos make of them."""

    def __init__(self, mesh: UnwrappedScan, size: int, painted: ColouredScan, graph: SceneGraph):
        texels = rasterize_atlas(mesh.corners, mesh.uv, np.zeros(len(mesh.triangles), dtype=np.int32), size)
        self.size, self.graph = size, graph
        self.rows, self.columns = texels.rows, texels.columns
        self.positions, self.normals = texels.positions, texels.normals
        distances, nearest = cKDTree(painted.vertices).query(self.positions, k=FALLBACK_NEIGHBOURS)
        self.fallback = _blended(to_linear(painted.colours), distances, nearest)
        patches = painted.sheet_patches if painted.sheet_patches is not None else np.zeros(len(painted.vertices), bool)
        self.patch = patches[nearest[:, 0]]
        self.blocks = _Blocks(self.positions)

    def weights(self, camera: PhotoCamera, photo: np.ndarray, detections: dict, indices: np.ndarray, buffer: np.ndarray):
        """This photo's view weight for each texel in `indices`, and where in the photo to sample it."""
        sized = camera.resized(photo.shape[1], photo.shape[0])
        mask = _people_mask(camera, photo, detections, buffer)
        weight, columns, rows = _weights_from(sized, self.positions[indices], self.normals[indices], buffer, mask)
        behind = np.flatnonzero((weight > 0) & self.patch[indices])
        if len(behind):
            hidden = hidden_behind_objects(self.graph, self.positions[indices[behind]], np.ones(len(behind), bool))(camera)
            weight[behind[hidden]] = 0.0
        return weight, columns, rows


def _blended(colours: np.ndarray, distances: np.ndarray, nearest: np.ndarray) -> np.ndarray:
    """Each texel's fallback as the inverse-distance mean of the nearest painted vertices.

    Copying the single nearest vertex tiles a patched floor in five-centimetre
    squares, because a patch's only vertices are the corners of its squares.
    """
    weights = 1.0 / np.maximum(distances, 1e-3)
    return ((weights[:, :, None] * colours[nearest]).sum(axis=1) / weights.sum(axis=1, keepdims=True)).astype(np.float32)


def _people_mask(camera: PhotoCamera, photo: np.ndarray, detections: dict, buffer: np.ndarray) -> np.ndarray | None:
    if not detections.get(camera.frame_id):
        return None
    mask = people_masks(detections, [camera], {camera.frame_id: photo.shape[:2]})[camera.frame_id]
    return _small_static_mask(mask, *buffer.shape)


def _exposure(surface: _Surface, cameras, frame_paths, detections) -> tuple[np.ndarray, list]:
    """Per-photo gains from an even sample of texels, and each photo's depth buffer for the bake."""
    sample = np.unique(np.linspace(0, len(surface.positions) - 1, MAX_EXPOSURE_POINTS).astype(np.int64))
    in_sample = np.full(len(surface.positions), -1, dtype=np.int64)
    in_sample[sample] = np.arange(len(sample))
    observations, buffers = [], []
    for camera in cameras:
        visible = surface.blocks.seen_by(camera)
        buffer = depth_buffer(camera, surface.positions[visible]) if len(visible) else None
        buffers.append(buffer)
        sampled = visible[in_sample[visible] >= 0] if buffer is not None else np.empty(0, np.int64)
        if not len(sampled):
            observations.append((np.empty(0, np.int64), np.empty((0, 3), np.float32)))
            continue
        photo = _read(frame_paths[camera.frame_id], EXPOSURE_PHOTO_EDGE)
        weight, columns, rows = surface.weights(camera, photo, detections, sampled, buffer)
        seen = np.flatnonzero(weight > 0)
        observations.append((in_sample[sampled[seen]], to_linear(bilinear(photo, columns[seen], rows[seen]))))
    return exposure_gains(observations, len(cameras), len(sample)), buffers


def _bake(surface: _Surface, cameras, frame_paths, detections, gains, buffers) -> tuple[np.ndarray, np.ndarray]:
    """Linear colour per texel and whether any photo reached it."""
    blend = TopViews(len(surface.positions), CONSENSUS_VIEWS)
    painted = np.zeros(len(surface.positions), dtype=bool)
    for camera, gain, buffer in zip(cameras, gains, buffers):
        if buffer is None:
            continue
        visible = surface.blocks.seen_by(camera)
        photo = _read(frame_paths[camera.frame_id], PHOTO_EDGE)
        weight, columns, rows = surface.weights(camera, photo, detections, visible, buffer)
        seen = np.flatnonzero(weight > 0)
        if not len(seen):
            continue
        colours = np.clip(to_linear(bilinear(photo, columns[seen], rows[seen])) * gain, 0.0, 1.0)
        blend.add(visible[seen], weight[seen], colours)
        painted[visible[seen]] = True
    return _in_chunks(agreed_colours, blend.weights, blend.colors), painted


def _in_chunks(resolve, weights: np.ndarray, colours: np.ndarray, size: int = 250_000) -> np.ndarray:
    """The resolution run a slice at a time, since comparing every pair of views is five-by-five per texel."""
    return np.concatenate([resolve(weights[start:start + size], colours[start:start + size])
                           for start in range(0, len(weights), size)] or [np.empty((0, 3), np.float32)])


def agreed_colours(weights: np.ndarray, colours: np.ndarray) -> np.ndarray:
    """The colour the most view weight agrees on, per texel, blended from the views that agree.

    People walk through a capture and the LiDAR rarely keeps them, so the photo
    with the best view of a stretch of floor can be the one with somebody
    standing on it. Taking that view because it is best paints them on the
    floor. Each kept view instead counts the weight of the views whose colour
    matches its own, and the most supported colour wins: a person one photo saw
    loses to the floor four photos saw. Within the winning group the best view
    still dominates, so detail comes from the sharpest photo that agrees.
    """
    distance = np.linalg.norm(colours[:, :, None, :] - colours[:, None, :, :], axis=3)
    support = ((distance <= AGREEMENT_DISTANCE) * weights[:, None, :]).sum(axis=2)
    winner = np.argmax(np.where(weights > 0, support, -1.0), axis=1)
    agreeing = (distance[np.arange(len(weights)), winner] <= AGREEMENT_DISTANCE) & (weights > 0)
    sharpened = np.where(agreeing, weights, 0.0) ** BLEND_SHARPNESS
    total = sharpened.sum(axis=1, keepdims=True)
    return ((sharpened[:, :, None] * colours).sum(axis=1) / np.maximum(total, 1e-12)).astype(np.float32)


def _atlas_image(surface: _Surface, colours: np.ndarray, painted: np.ndarray) -> Image.Image:
    linear = np.where(painted[:, None], colours, surface.fallback)
    image = np.zeros((surface.size, surface.size, 3), dtype=np.float32)
    image[surface.rows, surface.columns] = linear
    filled = np.zeros((surface.size, surface.size), dtype=bool)
    filled[surface.rows, surface.columns] = True
    return Image.fromarray(np.rint(to_srgb(pad_gutters(image, filled)) * 255).astype(np.uint8), "RGB")


def _write_glb(mesh_path: pathlib.Path, atlas_path: pathlib.Path, out_path: pathlib.Path) -> None:
    from ..blender import _run

    output = _run("texture_scan.py", ["--mesh", str(mesh_path), "--atlas", str(atlas_path), "--out", str(out_path)])
    if "SCAN_GLB_WRITTEN" not in output:
        raise RuntimeError(f"Blender did not write the textured scan:\n{output[-1500:]}")


def _evenly_spread(cameras: list[PhotoCamera], limit: int) -> list[PhotoCamera]:
    if len(cameras) <= limit:
        return cameras
    picks = np.linspace(0, len(cameras) - 1, limit).round().astype(int)
    return [cameras[index] for index in dict.fromkeys(picks.tolist())]


def bake_scan_atlas(
    painted: ColouredScan,
    graph: SceneGraph,
    cameras: list[PhotoCamera],
    frame_paths: dict[str, pathlib.Path],
    out_path: pathlib.Path,
    people: dict | None = None,
    max_triangles: int = 260_000,
) -> AtlasPaint:
    """The vertex-painted scan, thinned, unwrapped and baked from every photo into one textured glTF."""
    started = time.monotonic()
    chosen = _evenly_spread(cameras, MAX_ATLAS_PHOTOS)
    detections = people or {}
    with tempfile.TemporaryDirectory(prefix="standardphysics-atlas-") as temporary:
        work = pathlib.Path(temporary)
        mesh = unwrapped(painted, work, max_triangles)
        size = atlas_size(mesh)
        surface = _Surface(mesh, size, painted, graph)
        gains, buffers = _exposure(surface, chosen, frame_paths, detections)
        colours, reached = _bake(surface, chosen, frame_paths, detections, gains, buffers)
        atlas_path, mesh_path = work / "atlas.jpg", work / "mesh.npz"
        _atlas_image(surface, colours, reached).save(atlas_path, quality=ATLAS_JPEG_QUALITY)
        np.savez(mesh_path, vertices=mesh.vertices, triangles=mesh.triangles, uv=mesh.uv)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _write_glb(mesh_path, atlas_path, out_path)
    return AtlasPaint(out_path, float(reached.mean()) if len(reached) else 0.0, len(chosen), size, time.monotonic() - started)
