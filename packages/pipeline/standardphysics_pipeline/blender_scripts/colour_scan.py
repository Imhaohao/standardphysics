"""Runs inside Blender. Turns a coloured scan into a glTF the viewer can show.

    blender --background --python colour_scan.py -- --scan scan.npz --out scan.glb

Colour rides on the vertices, so the material is a plain diffuse shader reading
the colour attribute. Nothing is unwrapped and no image is written.
"""

import argparse
import sys

import bpy
import numpy as np

MAX_TRIANGLES = 260_000
"""Above this the viewer stutters on a phone, so the mesh is thinned to fit."""


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def build(vertices: np.ndarray, triangles: np.ndarray, colours: np.ndarray):
    mesh = bpy.data.meshes.new("scan")
    mesh.from_pydata(vertices.tolist(), [], triangles.tolist())
    mesh.validate()
    layer = mesh.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
    opaque = np.hstack([colours, np.ones((len(colours), 1), dtype=np.float32)])
    layer.data.foreach_set("color", opaque.ravel())
    obj = bpy.data.objects.new("scan", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def paint(obj) -> None:
    material = bpy.data.materials.new("scan")
    material.use_nodes = True
    tree = material.node_tree
    shader = tree.nodes.get("Principled BSDF")
    attribute = tree.nodes.new("ShaderNodeVertexColor")
    attribute.layer_name = "Col"
    tree.links.new(attribute.outputs["Color"], shader.inputs["Base Color"])
    shader.inputs["Roughness"].default_value = 0.9
    if "Specular IOR Level" in shader.inputs:
        shader.inputs["Specular IOR Level"].default_value = 0.1
    obj.data.materials.append(material)


def thin(obj, triangle_count: int) -> None:
    """Bring the scan down to something a phone can draw, colour and all."""
    if triangle_count <= MAX_TRIANGLES:
        return
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new("thin", "DECIMATE")
    modifier.ratio = MAX_TRIANGLES / triangle_count
    bpy.ops.object.modifier_apply(modifier="thin")
    print(f"THINNED {triangle_count} -> {len(obj.data.polygons)}")


def main() -> None:
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    archive = np.load(args.scan)
    obj = build(archive["vertices"], archive["triangles"], archive["colours"])
    paint(obj)
    thin(obj, len(archive["triangles"]))
    bpy.ops.export_scene.gltf(
        filepath=args.out, export_format="GLB", use_selection=False,
        export_yup=True, export_apply=True,
    )
    print("SCAN_GLB_WRITTEN")


main()
