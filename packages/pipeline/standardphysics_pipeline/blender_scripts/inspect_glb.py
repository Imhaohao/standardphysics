"""Read evaluated mesh bounds or a ray hit from a GLB inside Blender."""

import argparse
import json
import sys

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--ray", nargs=6, type=float)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.glb)
    if args.ray:
        origin = Vector(args.ray[:3])
        direction = Vector(args.ray[3:]).normalized()
        hit, location, _, _, obj, _ = bpy.context.scene.ray_cast(bpy.context.evaluated_depsgraph_get(), origin, direction)
        print(json.dumps({"hit": hit, "object": obj.name if hit else None, "location": list(location) if hit else None}))
        return

    obj = bpy.data.objects.get(args.node)
    if obj is None or obj.type != "MESH":
        print(json.dumps({"mesh": False}))
        return
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    points = [evaluated.matrix_world @ vertex.co for vertex in evaluated.data.vertices]
    print(json.dumps({
        "mesh": True,
        "min": [min(point[index] for point in points) for index in range(3)],
        "max": [max(point[index] for point in points) for index in range(3)],
    }))


if __name__ == "__main__":
    main()
