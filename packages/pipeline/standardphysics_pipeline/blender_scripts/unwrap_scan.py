"""Runs inside Blender. Thins a painted scan and unwraps it, so photographs can be baked into an image.

    blender --background --python unwrap_scan.py -- --scan scan.npz --out unwrapped.npz

The input holds room-frame vertices and triangles. The output holds the thinned
mesh's vertices and triangles and a UV pair for every corner of every triangle,
since a vertex on a seam between two islands has a different UV on each side.
"""

import argparse
import sys

import bmesh
import bpy
import numpy as np

MAX_TRIANGLES = 260_000
"""Above this the viewer stutters on a phone, so the mesh is thinned to fit."""
MARGIN_DIVISOR = 0.05
"""Space Blender leaves around each face, in its own relative units: two or three texels at 4096."""


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-triangles", type=int, default=MAX_TRIANGLES)
    return parser.parse_args(argv)


def build(vertices: np.ndarray, triangles: np.ndarray):
    mesh = bpy.data.meshes.new("scan")
    mesh.from_pydata(vertices.tolist(), [], triangles.tolist())
    mesh.validate()
    obj = bpy.data.objects.new("scan", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def thin(obj, max_triangles: int) -> None:
    count = len(obj.data.polygons)
    if count <= max_triangles:
        return
    modifier = obj.modifiers.new("thin", "DECIMATE")
    modifier.ratio = max_triangles / count
    bpy.ops.object.modifier_apply(modifier="thin")


def triangulated(obj) -> None:
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    bmesh.ops.triangulate(mesh, faces=mesh.faces[:])
    mesh.to_mesh(obj.data)
    mesh.free()


def unwrap(obj) -> None:
    """Every face packed on its own, at a size in proportion to its area.

    Charts that follow the surface are the usual choice, but a thinned LiDAR mesh
    is too noisy for them: it broke into so many tiny islands that the gaps
    between them took the atlas, and one texel covered eighteen centimetres.
    Packing faces one by one fills about a third of the atlas instead.
    """
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.lightmap_pack(PREF_CONTEXT="ALL_FACES", PREF_PACK_IN_ONE=True, PREF_MARGIN_DIV=MARGIN_DIVISOR)
    bpy.ops.object.mode_set(mode="OBJECT")


def corner_arrays(obj) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mesh = obj.data
    vertices = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", vertices)
    corners = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", corners)
    uv = np.empty(len(mesh.loops) * 2, dtype=np.float64)
    mesh.uv_layers.active.data.foreach_get("uv", uv)
    return vertices.reshape(-1, 3), corners.reshape(-1, 3), uv.reshape(-1, 3, 2)


def main() -> None:
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    archive = np.load(args.scan)
    obj = build(archive["vertices"], archive["triangles"])
    thin(obj, args.max_triangles)
    triangulated(obj)
    unwrap(obj)
    vertices, triangles, uv = corner_arrays(obj)
    np.savez(args.out, vertices=vertices, triangles=triangles, uv=uv)
    print(f"SCAN_UNWRAPPED {len(triangles)}")


main()
