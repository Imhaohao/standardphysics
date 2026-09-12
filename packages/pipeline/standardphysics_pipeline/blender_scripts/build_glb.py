"""Runs inside Blender. Builds display geometry from a SceneGraph and exports GLB.

    blender --background --python build_glb.py -- --graph g.json --out scene.glb

Geometry comes from the SceneGraph rather than from the scanned mesh, so the
thing the viewer draws is the thing the checks measured. A scanned USDZ is
prettier; it is also a separate surface that can disagree with the numbers.

glTF node names are arbitrary strings, so unlike USD these carry the node UUID
directly and the viewer can select by it with no mapping file.
"""

import argparse
import json
import sys

import bpy

KIND_ORDER = ["floor", "wall", "window", "opening", "door", "object"]


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def clear() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def rotation_z(matrix: list[float]) -> float:
    import math

    return math.atan2(matrix[4], matrix[0])


def add_node(node: dict) -> None:
    matrix = node["transform"]["m"]
    dimensions = node["dimensions"]
    bpy.ops.mesh.primitive_cube_add(
        size=1.0, location=(matrix[3], matrix[7], matrix[11])
    )
    obj = bpy.context.active_object
    obj.name = node["id"]
    obj.data.name = node["id"]
    obj.scale = (dimensions["x"], dimensions["y"], dimensions["z"])
    obj.rotation_euler = (0.0, 0.0, rotation_z(matrix))
    obj["kind"] = node["kind"]
    obj["label"] = node["label"]
    obj["movable"] = node["movable"]


def main() -> None:
    args = parse_args()
    graph = json.loads(open(args.graph).read())
    clear()

    nodes = sorted(
        graph["nodes"],
        key=lambda n: KIND_ORDER.index(n["kind"]) if n["kind"] in KIND_ORDER else 99,
    )
    for node in nodes:
        add_node(node)

    bpy.ops.export_scene.gltf(
        filepath=args.out,
        export_format="GLB",
        export_apply=True,
        export_extras=True,
        export_yup=True,
    )
    print(f"GLB_WRITTEN {args.out} nodes={len(nodes)}")


if __name__ == "__main__":
    main()
