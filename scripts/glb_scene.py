"""Direct GLB scene parsing for the rasterizer.

``scene_arrays`` used to go through the higher-level loader, which reshuffles
geometry across nodes for these multi-mesh soup GLBs (demonstrated in
runs/moffett/photo-mesh-500/r001/stageB evidence: raw chunk bounds correct,
loader geometry squeezed into a slab). This module reads POSITION, indices,
TEXCOORD_0 and the material's base colour image straight out of the GLB, in
document order.
"""
from __future__ import annotations

import base64
import json
import struct
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image


def _chunks(payload: bytes):
    offset = 12
    while offset + 8 <= len(payload):
        length, kind = struct.unpack_from("<II", payload, offset)
        offset += 8
        yield kind, payload[offset:offset + length]
        offset += length


def _component_reader(component_type: int):
    if component_type == 5126:
        return "<f4"
    if component_type == 5125:
        return "<u4"
    if component_type == 5123:
        return "<u2"
    if component_type == 5121:
        return "u1"
    raise ValueError(f"unsupported component type {component_type}")


def _read_accessor(document: dict, bin_blob: bytes, index: int) -> np.ndarray:
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    component = accessor.get("componentType", 5126)
    elements = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor.get("type", "VEC3")]
    count = accessor["count"]
    dtype = _component_reader(component)
    stride = view.get("byteStride", None)
    if stride is None:
        base = np.frombuffer(bin_blob[start:start + np.dtype(dtype).itemsize * elements * count], dtype=np.dtype(dtype))
        matrix = base.reshape(-1, elements)
    else:
        rows = np.zeros((count, elements), dtype=np.dtype(dtype))
        itemsize = np.dtype(dtype).itemsize
        for index_row in range(count):
            base = start + index_row * stride
            rows[index_row] = np.frombuffer(bin_blob[base:base + itemsize * elements], dtype=np.dtype(dtype))
        matrix = rows
    if component != 5126:
        matrix = matrix.astype(np.float32)
        normalized = accessor.get("normalized", False)
        maximum = {"<u1": 255.0, "u1": 255.0, "<u2": 65535.0, "u2": 65535.0,
                   "<u4": 4294967295.0, "u4": 4294967295.0}[dtype]
        if normalized:
            matrix = matrix / maximum
    return matrix


def _image_bytes(document: dict, bin_blob: bytes, image_meta: dict) -> bytes:
    """An embedded image's bytes, whether it sits in the buffer or in a data URI."""
    if "bufferView" in image_meta:
        view = document["bufferViews"][image_meta["bufferView"]]
        start = view.get("byteOffset", 0)
        return bin_blob[start:start + view["byteLength"]]
    return base64.b64decode(image_meta["uri"].split(",", 1)[1])


def _base_colour_image(
    document: dict,
    bin_blob: bytes,
    material: dict,
    textures_info: list,
    images: list,
    flip_images: bool,
) -> "np.ndarray | None":
    """One material's base colour texture, or None when it has none."""
    texture_index = material.get("pbrMetallicRoughness", {}).get("baseColorTexture", {}).get("index")
    if texture_index is None:
        return None
    info = textures_info[texture_index]
    if info.get("source") is None:
        return None
    raw = _image_bytes(document, bin_blob, images[info["source"]])
    image = np.asarray(Image.open(BytesIO(raw)).convert("RGB"), dtype=np.uint8)
    if flip_images:
        # legacy exports stored rows bottom-up relative to their TEXCOORDs
        image = np.ascontiguousarray(image[::-1])
    return image


def parse_scene(glb_path: Path):
    payload = glb_path.read_bytes()
    if payload[:4] != b"glTF":
        raise ValueError(f"not a GLB: {glb_path}")
    json_blob = bin_blob = None
    for kind, chunk in _chunks(payload):
        if kind == 0x4E4F534A:
            json_blob = chunk
        elif kind == 0x004E4942:
            bin_blob = chunk
    document = json.loads(json_blob)
    marker = (document.get("asset") or {}).get("extras") or {}
    flip_images = marker.get("photoMeshVersion") != 1
    meshes = []
    materials = document.get("materials", [])
    textures = []
    textures_info = document.get("textures", [])
    images = document.get("images", [])
    for material in materials:
        textures.append(
            _base_colour_image(document, bin_blob, material, textures_info, images, flip_images)
        )
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            vertices = _read_accessor(document, bin_blob, primitive["attributes"]["POSITION"]).astype(np.float32)
            faces = _read_accessor(document, bin_blob, primitive["indices"]).astype(np.int32).reshape(-1, 3)
            uv = None
            if "TEXCOORD_0" in primitive["attributes"]:
                uv = _read_accessor(document, bin_blob, primitive["attributes"]["TEXCOORD_0"]).astype(np.float32)
            else:
                uv = np.zeros((len(vertices), 2), dtype=np.float32)
            material_index = primitive.get("material")
            image = textures[material_index] if material_index is not None and material_index < len(textures) else None
            meshes.append((vertices, faces, uv, image))
    return meshes
