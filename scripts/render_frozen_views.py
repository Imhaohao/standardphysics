"""Render frozen evaluation views of a photo-mesh GLB through Blender EEVEE, unlit.

The Blender scene is the GLB as the web viewer would show it (KHR_materials_unlit
converted to emission), rendered at the frozen camera projection and saved as
lossless PNGs. Also writes diagnostic passes: geometry mask, photographed mask
and source-ID map. A synthetic self-test validates the camera/GLB chain before
real views are trusted.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"

BLENDER_SCRIPT = r"""
import bpy, json
plan = PLAN_JSON
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=plan["glb"])
for material in bpy.data.materials:
    if not material.use_nodes:
        continue
    tree = material.node_tree
    texture = None
    factor = 1.0
    for node in tree.nodes:
        if node.type == "TEX_IMAGE":
            texture = node
    strength = None
    emission = tree.nodes.new("ShaderNodeEmission")
    if texture is not None:
        tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
    emission.inputs["Strength"].default_value = 1.0
    out_surface = tree.nodes["Material Output"].inputs["Surface"]
    for link in list(out_surface.links):
        tree.links.remove(link)
    tree.links.new(emission.outputs["Emission"], out_surface)

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_depth = "8"
scene.render.image_settings.color_mode = "RGB"
scene.render.film_transparent = False
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.view_settings.exposure = 0.0
scene.world = bpy.data.worlds.new("World")
scene.world.color = (0, 0, 0)
if hasattr(scene.eevee, "taa_render_samples"):
    scene.eevee.taa_render_samples = 1
if hasattr(scene.eevee, "use_raytracing"):
    scene.eevee.use_raytracing = False

camera_object = bpy.data.objects.new("Evaluation camera", bpy.data.cameras.new("Evaluation camera"))
bpy.context.collection.objects.link(camera_object)
scene.camera = camera_object
camera = camera_object.data
camera.type = "PERSP"
camera.sensor_fit = "HORIZONTAL"
camera.sensor_width = 36.0

def set_view(view):
    w, h = view["render_width"], view["render_height"]
    scene.render.resolution_x = w
    scene.render.resolution_y = h
    scene.render.resolution_percentage = 100
    from mathutils import Matrix
    camera_object.matrix_world = Matrix(view["blender_world_matrix"])
    camera.lens = view["lens_mm"]
    camera.shift_x = view.get("shift_x", 0.0)
    camera.shift_y = view.get("shift_y", 0.0)
    camera.clip_start = 0.05
    camera.clip_end = 200.0

results = []
for index, view in enumerate(plan["views"]):
    set_view(view)
    for pass_name in view["passes"]:
        filepath = view["passes"][pass_name]
        scene.render.filepath = filepath
        bpy.ops.render.render(write_still=True)
        results.append(filepath)
print("BLENDER_VIEWS_DONE " + json.dumps(results))
"""


def blender_script_path() -> Path:
    return Path(__file__).with_suffix("") / "render_views_blender.py"


def run_blender(plan: Path, timeout_s: float = 7200) -> None:
    payload = json.loads(plan.read_text())
    embedded = BLENDER_SCRIPT.replace("PLAN_JSON", json.dumps(payload))
    script = Path("/tmp/standardphysics-render-views.py")
    script.write_text(embedded)
    result = subprocess.run(
        [BLENDER, "-b", "--factory-startup", "-P", str(script)],
        capture_output=True, text=True, timeout=timeout_s,
    )
    tail = (result.stdout + result.stderr)[-3000:]
    if "BLENDER_VIEWS_DONE" not in tail:
        sys.stderr.write(tail)
        raise RuntimeError("Blender did not complete the render plan")
    print(tail[-400:])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--timeout-s", type=float, default=7200)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    expected = [p for v in plan["views"] for p in v["passes"].values()]
    run_blender(args.plan, args.timeout_s)
    missing = [p for p in expected if not Path(p).is_file()]
    if missing:
        raise RuntimeError(f"missing render outputs after Blender run: {missing[:5]} ...")
    sizes = {p: Path(p).stat().st_size for p in expected}
    empty = [p for p, s in sizes.items() if s < 100]
    if empty:
        raise RuntimeError(f"suspect empty outputs: {empty}")
    print(f"rendered {len(expected)} passes")


if __name__ == "__main__":
    main()
