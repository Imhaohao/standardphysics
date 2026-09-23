"""Blender camera-pose renders of two GLBs for the furniture experiment."""

import argparse
import json
import sys

import bpy
from mathutils import Matrix, Vector


def arguments():
    argv = sys.argv[sys.argv.index("--") + 1:]
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--lidar", required=True)
    parser.add_argument("--fitted", required=True)
    parser.add_argument("--lidar-out", required=True)
    parser.add_argument("--fitted-out", required=True)
    return parser.parse_args(argv)


def camera_from(config):
    scene = bpy.context.scene
    width, height = config["width"], config["height"]
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    data = bpy.data.cameras.new("calibrated photo")
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = 36.0
    data.lens = config["fx"] * data.sensor_width / width
    data.shift_x = (width / 2 - config["cx"]) / width
    data.shift_y = (config["cy"] - height / 2) / width
    data.clip_start = 0.01
    data.clip_end = 100
    camera = bpy.data.objects.new("calibrated photo", data)
    scene.collection.objects.link(camera)
    room_to_camera = Matrix(config["room_to_camera"])
    camera.matrix_world = room_to_camera.inverted() @ Matrix.Diagonal((1, -1, -1, 1))
    scene.camera = camera
    return camera


def imported(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [obj for obj in bpy.context.scene.objects if obj not in before and obj.type == "MESH"]


def render(objects, other, path):
    for obj in objects:
        obj.hide_render = False
    for obj in other:
        obj.hide_render = True
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    args = arguments()
    config = json.load(open(args.config))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 8
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "PNG"
    camera = camera_from(config)
    light_data = bpy.data.lights.new("room light", "AREA")
    light_data.energy = 120
    light_data.shape = "DISK"
    light_data.size = 4
    light = bpy.data.objects.new("room light", light_data)
    scene.collection.objects.link(light)
    light.location = Vector(config["box_centre"]) + Vector((0, 0, 3))
    lidar = imported(args.lidar)
    fitted = imported(args.fitted)
    render(lidar, fitted, args.lidar_out)
    render(fitted, lidar, args.fitted_out)
    print("POSE_RENDERS_WRITTEN", camera.name)


main()
