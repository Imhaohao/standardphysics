"""Calibrated cameras for Blender's default glTF import of our room meshes.

The exporter writes (x, z, -y); Blender's glTF importer undoes that axis change.
Consequently Blender world is the original Z-up room, NOT glTF's Y-up world.
Pixel centres in PhotoCamera are integers; Blender's image bounds are at edges.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from .camera import ARKIT_TO_PIXEL_AXES, PhotoCamera


def blender_view(camera: PhotoCamera, crop: tuple[int, int, int, int], size: tuple[int, int]) -> dict:
    """Return JSON-ready Blender parameters plus independently projectable probes.

    Crop is (left, top, right, bottom) in the original image, then resize. No pose
    refinement is performed. Non-square focal lengths use Blender pixel aspect.
    """
    left, top, right, bottom = crop
    if not (0 <= left < right <= camera.width and 0 <= top < bottom <= camera.height):
        raise ValueError("crop must lie within the calibrated image")
    if any(not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in size):
        raise ValueError("render dimensions must be positive integers")
    cropped = replace(camera, cx=camera.cx-left, cy=camera.cy-top, width=right-left, height=bottom-top)
    view = cropped.resized(*size)
    world_to_pixel = np.asarray(view.room_to_camera)
    if world_to_pixel.shape != (4, 4) or not np.isfinite(world_to_pixel).all():
        raise ValueError("camera transform must be a finite 4x4 matrix")
    rotation = world_to_pixel[:3, :3]
    if (not np.allclose(world_to_pixel[3], [0, 0, 0, 1], atol=1e-6)
            or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5)
            or not np.isclose(np.linalg.det(rotation), 1, atol=1e-5)):
        raise ValueError("camera transform must be a proper rigid transform")
    if not np.isfinite([view.fx, view.fy, view.cx, view.cy]).all() or min(view.fx, view.fy) <= 0:
        raise ValueError("camera intrinsics must be finite with positive focal lengths")
    inverse = np.linalg.inv(world_to_pixel)
    matrix = inverse @ ARKIT_TO_PIXEL_AXES
    aspect = view.fx / view.fy
    probes = []
    for depth in (0.7, 2.0, 5.0):
        for u, v in ((0, 0), (view.width-1, 0), (0, view.height-1),
                     (view.width-1, view.height-1), ((view.width-1)/2, (view.height-1)/2)):
            local = np.array([(u-view.cx)/view.fx*depth, (v-view.cy)/view.fy*depth, depth, 1])
            probes.append({"room_point": (inverse @ local)[:3].tolist(), "pixel": [u, v]})
    return {
        "id": view.frame_id, "width": view.width, "height": view.height,
        "crop": list(crop), "matrix_world": matrix.tolist(),
        "lens_mm": view.fx * 36.0 / view.width,
        "shift_x": (view.width/2 - (view.cx+0.5)) / view.width,
        "shift_y": ((view.cy+0.5) - view.height/2) * aspect / view.width,
        "pixel_aspect_x": max(1.0, 1.0/aspect), "pixel_aspect_y": max(1.0, aspect),
        "fx": view.fx, "fy": view.fy, "cx": view.cx, "cy": view.cy,
        "verification_points": probes,
    }
