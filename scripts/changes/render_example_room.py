"""Render two handheld walkthroughs of one furnished room, with furniture changed in between.

Run inside Blender, naming one of the rooms in example_scenes.py:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P scripts/changes/render_example_room.py -- \
        --scene living-room --out datasets/changes/living-room

Every model and texture is CC0 from Poly Haven and is downloaded once into
~/.cache/sp-changes/polyhaven. The script writes before.mp4, after.mp4 and truth.json,
which records each object's box in both recordings and every rendered camera pose.

The footage imitates a phone: the camera shakes and rolls in the hand, the shutter blurs
motion and reads the sensor top to bottom, the exposure drifts, and the video carries
grain and compression.
"""

import argparse
import json
import math
import pathlib
import random
import shutil
import subprocess
import sys
import urllib.request

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from example_scenes import SCENES  # noqa: E402

CACHE = pathlib.Path.home() / ".cache" / "sp-changes" / "polyhaven"
API = "https://api.polyhaven.com/files/"
WIDTH, HEIGHT = 960, 720
FPS = 16
SECONDS = 6


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", choices=sorted(SCENES), default="living-room")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--preview", action="store_true", help="render one still per recording")
    return parser.parse_args(argv)


def fetch(url: str, target: pathlib.Path) -> pathlib.Path:
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "standardphysics-room-changes/0.1"})
        with urllib.request.urlopen(request) as response, open(target, "wb") as out:
            shutil.copyfileobj(response, out)
    return target


def files_for(asset_id: str) -> dict:
    listing = CACHE / f"{asset_id}.json"
    if not listing.exists():
        fetch(API + asset_id, listing)
    return json.loads(listing.read_text())


def fetch_model(asset_id: str) -> pathlib.Path:
    entry = files_for(asset_id)["gltf"]["1k"]["gltf"]
    folder = CACHE / asset_id
    for relative, item in entry.get("include", {}).items():
        fetch(item["url"], folder / relative)
    return fetch(entry["url"], folder / pathlib.Path(entry["url"]).name)


def fetch_texture(asset_id: str) -> dict[str, pathlib.Path]:
    files = files_for(asset_id)
    colour_key = "Diffuse" if "Diffuse" in files else sorted(key for key in files if key.startswith("col"))[0]
    maps = {"color": colour_key, "normal": "nor_gl", "rough": "Rough"}
    return {
        role: fetch(files[key]["1k"]["jpg"]["url"], CACHE / asset_id / f"{role}.jpg")
        for role, key in maps.items()
    }


def use_metal_gpu(scene) -> None:
    scene.cycles.device = "GPU"
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = "METAL"
    preferences.get_devices()
    for device in preferences.devices:
        device.use = True


def phone_shutter(scene) -> None:
    """Half-frame motion blur read out top to bottom, the way a phone sensor exposes."""
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    scene.cycles.rolling_shutter_type = "TOP"
    scene.cycles.rolling_shutter_duration = 0.3


def reset_scene(samples: int) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
    scene.render.fps = FPS
    use_metal_gpu(scene)
    phone_shutter(scene)
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.use_persistent_data = True
    scene.view_settings.view_transform = "AgX"
    scene.world = bpy.data.worlds.new("world")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.8, 0.9, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.25


def textured_material(name: str, asset_id: str, tile_m: float) -> bpy.types.Material:
    maps = fetch_texture(asset_id)
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    shader = nodes["Principled BSDF"]
    coords = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1 / tile_m, 1 / tile_m, 1 / tile_m)
    links.new(coords.outputs["Object"], mapping.inputs["Vector"])
    images = {}
    for role, path in maps.items():
        node = nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(str(path))
        node.projection = "BOX"
        node.projection_blend = 0.2
        if role != "color":
            node.image.colorspace_settings.name = "Non-Color"
        links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        images[role] = node
    links.new(images["color"].outputs["Color"], shader.inputs["Base Color"])
    links.new(images["rough"].outputs["Color"], shader.inputs["Roughness"])
    normal = nodes.new("ShaderNodeNormalMap")
    links.new(images["normal"].outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], shader.inputs["Normal"])
    return material


def box(name: str, size: tuple, location: tuple, material: bpy.types.Material) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(scale=True)
    obj.data.materials.append(material)
    return obj


def build_room(room: dict) -> None:
    x, y, z = room["half_x"], room["half_y"], room["height"]
    floor = textured_material("floor", room["floor"], 1.6)
    wall = textured_material("wall", room["wall"], 1.4)
    rug_texture, rug_size, rug_centre = room["rug"]
    rug = textured_material("rug", rug_texture, 0.6)
    thickness = 0.1
    box("floor", (2 * x + 0.2, 2 * y + 0.2, thickness), (0, 0, -thickness / 2), floor)
    box("ceiling", (2 * x + 0.2, 2 * y + 0.2, thickness), (0, 0, z + thickness / 2), wall)
    box("wall_back", (2 * x, thickness, z), (0, y + thickness / 2, z / 2), wall)
    box("wall_front", (2 * x, thickness, z), (0, -y - thickness / 2, z / 2), wall)
    box("wall_left", (thickness, 2 * y, z), (-x - thickness / 2, 0, z / 2), wall)
    box("wall_right", (thickness, 2 * y, z), (x + thickness / 2, 0, z / 2), wall)
    box("rug", (*rug_size, 0.008), (*rug_centre, 0.004), rug)
    add_door_and_window(x, y)
    add_lights(x, z)


def flat_material(name: str, color: tuple, emission: float = 0.0) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = 0.55
    if emission:
        shader.inputs["Emission Color"].default_value = (*color, 1)
        shader.inputs["Emission Strength"].default_value = emission
    return material


def add_door_and_window(x: float, y: float) -> None:
    door = flat_material("door", (0.32, 0.22, 0.15))
    trim = flat_material("trim", (0.9, 0.88, 0.84))
    box("door", (0.9, 0.04, 2.05), (-x + 1.2, -y + 0.01, 1.025), door)
    box("door_trim", (1.02, 0.03, 2.12), (-x + 1.2, -y + 0.005, 1.06), trim)
    sky = flat_material("window_light", (0.85, 0.92, 1.0), emission=6.0)
    box("window", (0.03, 1.5, 1.2), (x - 0.03, 0.75, 1.55), sky)
    box("window_frame", (0.04, 1.62, 1.32), (x - 0.005, 0.75, 1.55), trim)


def add_lights(x: float, z: float) -> None:
    bpy.ops.object.light_add(type="AREA", location=(0, 0.2, z - 0.05))
    ceiling = bpy.context.active_object
    ceiling.data.energy = 450
    ceiling.data.size = 1.6
    ceiling.data.color = (1.0, 0.93, 0.84)
    bpy.ops.object.light_add(type="AREA", location=(x - 0.3, 0.75, 1.55), rotation=(0, -math.pi / 2, 0))
    window = bpy.context.active_object
    window.data.energy = 260
    window.data.size = 1.4
    window.data.color = (0.86, 0.92, 1.0)
    for light in (ceiling, window):
        light.visible_camera = False


def import_model(name: str, asset_id: str) -> bpy.types.Object:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(fetch_model(asset_id)))
    imported = [obj for obj in bpy.data.objects if obj not in before]
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    for obj in imported:
        if obj.parent is None:
            obj.parent = root
    return root


def meshes_under(root: bpy.types.Object) -> list:
    return [obj for obj in root.children_recursive if obj.type == "MESH"]


def world_bounds(root: bpy.types.Object) -> tuple[Vector, Vector]:
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(corner) for obj in meshes_under(root) for corner in obj.bound_box]
    low = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    high = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return low, high


def local_extent(root: bpy.types.Object) -> dict:
    """Footprint and height in the object's own frame, before any yaw is applied."""
    root.matrix_world = Matrix.Identity(4)
    low, high = world_bounds(root)
    return {"low": low.copy(), "high": high.copy()}


def place(root: bpy.types.Object, extent: dict, placement: tuple, support_tops: dict) -> None:
    x, y, yaw = placement[:3]
    centre = (extent["low"] + extent["high"]) / 2
    base_z = support_tops[placement[3]] if len(placement) > 3 else 0.0
    rotation = Matrix.Rotation(math.radians(yaw), 4, "Z")
    to_centre = Matrix.Translation((-centre.x, -centre.y, -extent["low"].z))
    root.matrix_world = Matrix.Translation((x, y, base_z + 0.002)) @ rotation @ to_centre


def set_visible(root: bpy.types.Object, visible: bool) -> None:
    for obj in [root, *root.children_recursive]:
        obj.hide_render = not visible
        obj.hide_viewport = not visible


def oriented_box(root: bpy.types.Object, extent: dict, placement: tuple) -> dict:
    low, high = world_bounds(root)
    size = extent["high"] - extent["low"]
    return {
        "center": [round(v, 4) for v in ((low + high) / 2)],
        "size": [round(size.x, 4), round(size.y, 4), round(size.z, 4)],
        "yaw_deg": placement[2],
        "aabb_min": [round(v, 4) for v in low],
        "aabb_max": [round(v, 4) for v in high],
    }


def hang_frame(room: dict) -> None:
    root = import_model("frame", "hanging_picture_frame_01")
    extent = local_extent(root)
    centre = (extent["low"] + extent["high"]) / 2
    root.matrix_world = Matrix.Translation((0.0, room["half_y"] - 0.02, 1.62)) @ Matrix.Translation(-centre)


def stage(objects: list, models: dict, epoch: int) -> dict:
    """Pose every object for one recording and return the box of each one present."""
    tops, boxes = {}, {}
    ordered = sorted(objects, key=lambda spec: len(spec[3 + epoch] or ()) > 3)
    for name, _, _, *placements in ordered:
        root, extent = models[name]
        placement = placements[epoch]
        set_visible(root, placement is not None)
        if placement is None:
            continue
        place(root, extent, placement, tops)
        tops[name] = world_bounds(root)[1].z
        boxes[name] = oriented_box(root, extent, placement)
    return boxes


def smooth(t: float) -> float:
    return t * t * (3 - 2 * t)


def along(keys: list, t: float) -> tuple[Vector, Vector]:
    span = t * (len(keys) - 1)
    index = min(int(span), len(keys) - 2)
    mix = smooth(span - index)
    (p0, l0), (p1, l1) = keys[index], keys[index + 1]
    return Vector(p0).lerp(Vector(p1), mix), Vector(l0).lerp(Vector(l1), mix)


def handheld_shake(rng: random.Random) -> callable:
    phases = [rng.uniform(0, 2 * math.pi) for _ in range(9)]

    def offset(t: float) -> tuple[Vector, float]:
        wobble = [math.sin(2 * math.pi * f * t * SECONDS + p) for f, p in zip([0.7, 1.3, 2.1] * 3, phases)]
        position = Vector((wobble[0], wobble[1], wobble[2])) * 0.012
        roll = 0.02 * wobble[3] + 0.01 * wobble[4]
        return position, roll

    return offset


def camera_matrix(position: Vector, target: Vector, roll: float) -> Matrix:
    forward = (target - position).normalized()
    rotation = forward.to_track_quat("-Z", "Y").to_matrix().to_4x4()
    return Matrix.Translation(position) @ rotation @ Matrix.Rotation(roll, 4, "Z")


def opencv_pose(matrix: Matrix) -> list:
    flip = Matrix.Diagonal((1, -1, -1, 1))
    return [[round(v, 6) for v in row] for row in (matrix @ flip)]


def animate_camera(camera: bpy.types.Object, keys: list, seed: str, frames: int) -> list:
    shake = handheld_shake(random.Random(seed))
    view = bpy.context.scene.view_settings
    drift = random.Random(seed + "exposure").uniform(0, 2 * math.pi)
    poses = []
    for frame in range(frames):
        t = frame / max(frames - 1, 1)
        position, target = along(keys, t)
        jitter, roll = shake(t)
        camera.matrix_world = camera_matrix(position + jitter, target, roll)
        camera.keyframe_insert("location", frame=frame + 1)
        camera.keyframe_insert("rotation_euler", frame=frame + 1)
        view.exposure = 0.25 * math.sin(2 * math.pi * 0.35 * t * SECONDS + drift)
        view.keyframe_insert("exposure", frame=frame + 1)
        poses.append(opencv_pose(camera.matrix_world))
    return poses


def intrinsics(camera: bpy.types.Object) -> list:
    focal_px = camera.data.lens / camera.data.sensor_width * WIDTH
    return [[focal_px, 0, WIDTH / 2], [0, focal_px, HEIGHT / 2], [0, 0, 1]]


def render_walk(camera: bpy.types.Object, keys: list, walk: str, out: pathlib.Path, preview: bool) -> list:
    scene = bpy.context.scene
    frames = 1 if preview else SECONDS * FPS
    camera.animation_data_clear()
    scene.animation_data_clear()
    poses = animate_camera(camera, keys, f"{out.name}-{walk}", frames)
    frames_dir = out / f"frames_{walk}"
    scene.frame_start, scene.frame_end = 1, frames
    scene.render.filepath = str(frames_dir / "f_")
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(animation=True)
    if not preview:
        encode_video(frames_dir, out / f"{walk}.mp4")
    return poses


def encode_video(frames_dir: pathlib.Path, target: pathlib.Path) -> None:
    command = [
        "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames_dir / "f_%04d.png"),
        "-vf", "noise=alls=6:allf=t", "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", str(target),
    ]
    subprocess.run(command, check=True)
    shutil.rmtree(frames_dir)


def change_kind(first: dict | None, second: dict | None) -> str | None:
    if first and not second:
        return "removed"
    if second and not first:
        return "added"
    if first and second and first["center"] != second["center"]:
        return "moved"
    return None


def truth_record(scene_spec: dict, boxes: list[dict], cameras: dict, camera: bpy.types.Object) -> dict:
    labels = {name: label for name, _, label, *_ in scene_spec["objects"]}
    hidden = set(scene_spec["unverifiable"])
    changes, unverifiable = [], []
    for name in labels:
        first, second = boxes[0].get(name), boxes[1].get(name)
        kind = change_kind(first, second)
        if kind:
            entry = {"object": name, "label": labels[name], "type": kind, "before": first, "after": second}
            (unverifiable if name in hidden else changes).append(entry)
    room = scene_spec["room"]
    return {
        "frame": "Blender world, metres, z up, floor at z = 0",
        "room": {"x": [-room["half_x"], room["half_x"]], "y": [-room["half_y"], room["half_y"]],
                 "height": room["height"]},
        "fps": FPS,
        "intrinsics": intrinsics(camera),
        "cameras_opencv_c2w": cameras,
        "objects": {name: {"label": labels[name], "before": boxes[0].get(name), "after": boxes[1].get(name)}
                    for name in labels},
        "changes": changes,
        "unverifiable": unverifiable,
    }


def main() -> None:
    args = parse_args()
    spec = SCENES[args.scene]
    args.out.mkdir(parents=True, exist_ok=True)
    reset_scene(args.samples)
    build_room(spec["room"])
    hang_frame(spec["room"])
    models = {}
    for name, asset_id, *_ in spec["objects"]:
        root = import_model(name, asset_id)
        models[name] = (root, local_extent(root))
    bpy.ops.object.camera_add()
    camera = bpy.context.active_object
    camera.data.lens, camera.data.sensor_width = 26, 36
    bpy.context.scene.camera = camera
    boxes, cameras = [], {}
    for epoch, walk in enumerate(["before", "after"]):
        boxes.append(stage(spec["objects"], models, epoch))
        cameras[walk] = render_walk(camera, spec["walks"][walk], walk, args.out, args.preview)
    if not args.preview:
        (args.out / "truth.json").write_text(json.dumps(truth_record(spec, boxes, cameras, camera), indent=1))


main()
