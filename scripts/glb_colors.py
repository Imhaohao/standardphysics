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


def glb_vertex_colors(path: Path) -> list[np.ndarray]:
    payload = path.read_bytes()
    if payload[:4] != b"glTF":
        return []
    header = struct.unpack_from("<III", payload, 0)
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
            view = buffer_views[accessor.get("bufferView")]
            start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            if "byteStride" in view:
                stride = view["byteStride"]
            else:
                stride = None
            component = accessor.get("componentType", COMPONENT_FLOAT)
            element_count = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor.get("type", "VEC3")]
            count = accessor.get("count", 0)
            if component == COMPONENT_FLOAT:
                dtype = np.float32
                size = 4
            elif component == COMPONENT_UBYTE:
                dtype = np.float32
                size = 1
                normalized = accessor.get("normalized", False)
            else:
                continue
            if stride is None:
                stride = size * element_count
            rows = np.zeros((count, 3), dtype=np.float32)
            for index in range(count):
                base = start + index * stride
                values = np.frombuffer(bin_blob[base:base + size * element_count], dtype=np.dtype(dtype))
                if component == COMPONENT_UBYTE and normalized:
                    values = values / 255.0
                if component == COMPONENT_UBYTE and not normalized:
                    values = values.astype(np.float32)
                rows[index, :min(3, element_count)] = values[:min(3, element_count)]
            arrays.append(rows)
    return arrays
