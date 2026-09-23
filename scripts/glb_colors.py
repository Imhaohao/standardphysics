"""Minimal GLB inspection: pull per-primitive COLOR_0 vertex attributes.

trimesh does not always surface glTF vertex colour attributes (FLOAT_COLOR
COLOR_0), so the rasterizer reads them straight out of the GLB chunks.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

COMPONENT_FLOAT = 5126
COMPONENT_UBYTE = 5121
COMPONENT_USHORT = 5123


def _glb_chunks(payload: bytes) -> tuple[bytes | None, bytes | None]:
    """The JSON and binary chunks of a GLB container, in that order."""
    offset = 12
    json_blob = None
    bin_blob = None
    for _ in range(2):
        length, kind = struct.unpack_from("<II", payload, offset)
        offset += 8
        chunk = payload[offset:offset + length]
        offset += length
        if kind == 0x4E4F534A:
            json_blob = chunk
        elif kind == 0x004E4942:
            bin_blob = chunk
    return json_blob, bin_blob


def _colour_layout(accessor: dict, view: dict) -> tuple | None:
    """How one COLOR_0 accessor is packed, or None for a component we cannot read."""
    component = accessor.get("componentType", COMPONENT_FLOAT)
    if component == COMPONENT_FLOAT:
        dtype, size, normalized = np.float32, 4, False
    elif component == COMPONENT_UBYTE:
        dtype, size, normalized = np.float32, 1, accessor.get("normalized", False)
    else:
        return None
    element_count = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor.get("type", "VEC3")]
    stride = view.get("byteStride", size * element_count)
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return component, dtype, size, normalized, element_count, stride, start


def _colour_rows(accessor: dict, view: dict, bin_blob: bytes) -> np.ndarray | None:
    """The RGB rows of one COLOR_0 accessor, alpha dropped."""
    layout = _colour_layout(accessor, view)
    if layout is None:
        return None
    component, dtype, size, normalized, element_count, stride, start = layout
    count = accessor.get("count", 0)
    width = min(3, element_count)
    rows = np.zeros((count, 3), dtype=np.float32)
    for index in range(count):
        base = start + index * stride
        values = np.frombuffer(bin_blob[base:base + size * element_count], dtype=np.dtype(dtype))
        if component == COMPONENT_UBYTE:
            values = values / 255.0 if normalized else values.astype(np.float32)
        rows[index, :width] = values[:width]
    return rows


def glb_vertex_colors(path: Path) -> list[np.ndarray]:
    payload = path.read_bytes()
    if payload[:4] != b"glTF":
        return []
    json_blob, bin_blob = _glb_chunks(payload)
    if json_blob is None or bin_blob is None:
        return []
    document = json.loads(json_blob.decode("utf-8"))
    accessors = document.get("accessors", [])
    buffer_views = document.get("bufferViews", [])
    arrays: list[np.ndarray] = []
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            colour = primitive.get("attributes", {}).get("COLOR_0")
            if colour is None:
                continue
            accessor = accessors[colour]
            rows = _colour_rows(accessor, buffer_views[accessor.get("bufferView")], bin_blob)
            if rows is not None:
                arrays.append(rows)
    return arrays
