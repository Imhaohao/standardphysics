"""Write the photo-mesh GLB directly from the run's arrays.

The generic mesh exporter mangles these multi-node soup GLBs (see r001
evidence: exported vertex sets share no coordinates with the decimation cache
they were built from, and arrive back signed-permuted). This writer controls
every byte: positions are (x, z, -y) float32, TEXCOORD_0 is photo-native
(v=0 at the photo's top row), sampling is linear clamp, materials are unlit
and double-sided, and each camera group keeps its own cropped full-resolution
JPEG. A version marker in the GLB extras distinguishes this convention from
legacy exports in the raster loader.
"""
from __future__ import annotations

import base64
import json
import struct
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

VERSION = 1


def _jpeg_bytes(image: np.ndarray) -> bytes:
    buffer = BytesIO()
    Image.fromarray(image.astype(np.uint8), "RGB").save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _pad4(data: bytearray) -> None:
    while len(data) % 4:
        data.append(0)


class GlbBuilder:
    def __init__(self):
        self.bin = bytearray()
        self.buffer_views = []
        self.accessors = []
        self.meshes = []
        self.materials = []
        self.textures = []
        self.images = []
        self.nodes = []
        self.neutral_material_index = None

    def _view(self, data: bytes, target=None) -> int:
        _pad4(self.bin)
        offset = len(self.bin)
        self.bin += data
        _pad4(self.bin)
        length = len(data)
        index = len(self.buffer_views)
        if target is not None:
            index = target
        else:
            self.buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": length})
        return index

    def accessor(self, array: np.ndarray, view_index: int, kind: str) -> int:
        component = {np.dtype(np.float32): 5126, np.dtype(np.uint32): 5125,
                     np.dtype(np.uint16): 5123}[array.dtype]
        count = int(array.size) if kind == "SCALAR" else int(array.shape[0])
        self.accessors.append({
            "bufferView": view_index, "componentType": component, "count": int(count),
            "type": kind,
        })
        if kind == "VEC3" and component == 5126:
            self.accessors[-1]["min"] = array.min(axis=0).astype(float).tolist()
            self.accessors[-1]["max"] = array.max(axis=0).astype(float).tolist()
        return len(self.accessors) - 1

    def add_neutral_material(self, colour=(0.62, 0.60, 0.58)):
        index = len(self.materials)
        self.materials.append({
            "pbrMetallicRoughness": {"baseColorFactor": [*colour, 1.0], "metallicFactor": 0.0,
                                     "roughnessFactor": 1.0},
            "doubleSided": True, "extensions": {"KHR_materials_unlit": {}},
        })
        self.neutral_material_index = index
        return index

    def add_textured_mesh(self, vertices: np.ndarray, faces: np.ndarray, uv: np.ndarray,
                          photo: np.ndarray, name: str) -> int:
        positions = vertices.astype(np.float32).tobytes()
        indices = faces.astype(np.uint32).tobytes()
        texcoords = uv.astype(np.float32).tobytes()
        jpeg = _jpeg_bytes(photo)
        position_view = self._view(positions)
        index_view = self._view(indices)
        uv_view = self._view(texcoords)
        image_view = self._view(jpeg)
        position_accessor = self.accessor(vertices.astype(np.float32), position_view, "VEC3")
        index_accessor = self.accessor(faces.astype(np.uint32), index_view, "SCALAR")
        uv_accessor = self.accessor(uv.astype(np.float32), uv_view, "VEC2")
        image_index = len(self.images)
        self.images.append({"bufferView": image_view, "mimeType": "image/jpeg"})
        texture_index = len(self.textures)
        self.textures.append({"source": image_index, "sampler": 0})
        material_index = len(self.materials)
        self.materials.append({
            "pbrMetallicRoughness": {"baseColorTexture": {"index": texture_index},
                                     "metallicFactor": 0.0, "roughnessFactor": 1.0},
            "doubleSided": True, "extensions": {"KHR_materials_unlit": {}},
        })
        mesh_index = len(self.meshes)
        self.meshes.append({
            "primitives": [{"attributes": {"POSITION": position_accessor, "TEXCOORD_0": uv_accessor},
                            "indices": index_accessor, "material": material_index, "mode": 4}],
        })
        node_index = len(self.nodes)
        self.nodes.append({"name": name, "mesh": mesh_index})
        return node_index

    def add_neutral_mesh(self, vertices: np.ndarray, faces: np.ndarray, name: str) -> int:
        positions = vertices.astype(np.float32).tobytes()
        indices = faces.astype(np.uint32).tobytes()
        position_view = self._view(positions)
        index_view = self._view(indices)
        position_accessor = self.accessor(vertices.astype(np.float32), position_view, "VEC3")
        index_accessor = self.accessor(faces.astype(np.uint32), index_view, "SCALAR")
        mesh_index = len(self.meshes)
        self.meshes.append({
            "primitives": [{"attributes": {"POSITION": position_accessor},
                            "indices": index_accessor, "material": self.neutral_material_index, "mode": 4}],
        })
        node_index = len(self.nodes)
        self.nodes.append({"name": name, "mesh": mesh_index})
        return node_index

    def build(self) -> bytes:
        _pad4(self.bin)
        document = {
            "asset": {"version": "2.0", "generator": "standardphysics-photo-mesh", "extras": {"photoMeshVersion": VERSION}},
            "extensionsUsed": ["KHR_materials_unlit"],
            "scene": 0,
            "scenes": [{"nodes": list(range(len(self.nodes)))}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "textures": self.textures,
            "images": self.images,
            "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [{"byteLength": len(self.bin)}],
        }
        json_blob = json.dumps(document, separators=(",", ":")).encode("utf-8")
        json_padded = json_blob + b" " * ((4 - len(json_blob) % 4) % 4)
        header = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(json_padded) + 8 + len(self.bin))
        chunks = (struct.pack("<II", len(json_padded), 0x4E4F534A) + json_padded +
                  struct.pack("<II", len(self.bin), 0x004E4942) + bytes(self.bin))
        return header + chunks


def material_photo_from_jpeg(jpeg_path: Path) -> np.ndarray:
    return np.asarray(Image.open(jpeg_path).convert("RGB"), dtype=np.uint8)


def neutral_colour_bytes():
    return np.array([158, 153, 148], dtype=np.uint8)
